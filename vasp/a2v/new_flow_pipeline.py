from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from vasp.core.serializer_v3 import write_element3_txt_from_media_json
from vasp.media_reader.from_captions import create_media_json_from_captions_file
from vasp.planner.cli_combined import call_planner_endpoint
from vasp.planner.combined_prompt_builder import generate_combined_planner_input_prompt
from vasp.refiner.segment_inference_runner import run_refiner_for_segment_prompts
from vasp.refiner.segment_output_renderer import render_segment_outputs_to_video
from vasp.refiner.segment_prompt_builder import build_segmented_refiner_prompts


def run_new_flow_pipeline(
    *,
    edit_name: str,
    captions_file: str | Path,
    user_instruction: str,
    planner_endpoint: str,
    refiner_endpoint: str,
    user_theme_instruction: str | None = None,
    static_dir: str | Path = "vasp/utility_files",
    output_root: str | Path = "output/edits",
) -> dict[str, str]:
    static_paths = _ensure_static_utility_files(Path(static_dir))
    run_dir = Path(output_root) / _safe_name(edit_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[A2V_PIPELINE] Run dir: {run_dir}")

    # 1) captions + media folder -> media.json (and internal ASR/analysis)
    print("[A2V_PIPELINE][1/10] Reading captions/media -> media.json")
    media_json = create_media_json_from_captions_file(
        captions_file_path=captions_file,
        output_media_json_path=run_dir / "media.json",
        instruction=user_instruction,
    )
    media_json_path = run_dir / "media.json"
    media_json_path.write_text(json.dumps(media_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[A2V_PIPELINE] media.json written: {media_json_path}")

    # word mapping output (permanent for each edit run)
    print("[A2V_PIPELINE][2/10] Extracting word timing map")
    word_map_all = _extract_word_map_all(media_json)
    word_map_all_path = run_dir / "word_timing_map_all.json"
    word_map_all_path.write_text(json.dumps(word_map_all, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also keep compatibility copy where existing tools look by default.
    compat_dir = Path("output/word_timing_maps")
    compat_dir.mkdir(parents=True, exist_ok=True)
    (compat_dir / "word_timing_map_all.json").write_text(
        json.dumps(word_map_all, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[A2V_PIPELINE] word_timing_map_all written: {word_map_all_path}")

    # 2) media_understanding + media.json -> element.txt
    print("[A2V_PIPELINE][3/10] Serializing media understanding -> element.txt")
    element_txt = write_element3_txt_from_media_json(
        media_json_path=media_json_path,
        output_path=run_dir / "element.txt",
        media_understanding_md_path=static_paths["media_understanding"],
    )

    # 3) planner combined prompt
    print("[A2V_PIPELINE][4/10] Building planner combined prompt")
    planner_input_prompt = generate_combined_planner_input_prompt(
        system_prompt_path=static_paths["planner_system_prompt"],
        transcript=None,  # auto-extracted from media.json
        user_instruction=user_instruction,
        user_specific_instruction=user_theme_instruction,
        element3_path=element_txt,
        output_schema_path=static_paths["planner_output_schema"],
        output_prompt_path=run_dir / "planner_combined_input.txt",
        media_json_path=media_json_path,
    )

    # 4) planner endpoint -> planner output
    print("[A2V_PIPELINE][5/10] Calling planner endpoint")
    planner_txt_path = run_dir / "planner_output.txt"
    planner_meta_path = run_dir / "planner_output.meta.json"
    call_planner_endpoint(
        endpoint=planner_endpoint,
        prompt_path=planner_input_prompt,
        output_text_path=planner_txt_path,
        output_meta_path=planner_meta_path,
        temperature=0.1,
        max_tokens=2400,
        timeout_s=420.0,
    )
    print(f"[A2V_PIPELINE] planner output written: {planner_txt_path}")

    # 5) per-segment refiner prompts
    print("[A2V_PIPELINE][6/10] Building per-segment refiner prompts")
    refiner_prompt_dir = run_dir / "refiner_segment_prompts"
    build_segmented_refiner_prompts(
        system_prompt_path=static_paths["refiner_system_prompt"],
        planner_output_path=planner_txt_path,
        media_json_path=media_json_path,
        output_schema_path=static_paths["refiner_output_schema"],
        output_dir=refiner_prompt_dir,
    )

    # 6) per-segment refiner outputs
    print("[A2V_PIPELINE][7/10] Calling refiner endpoint per segment")
    refiner_output_dir = run_dir / "refiner_segment_outputs"
    run_refiner_for_segment_prompts(
        prompts_dir=refiner_prompt_dir,
        endpoint=refiner_endpoint,
        output_dir=refiner_output_dir,
        temperature=0.1,
        max_tokens=2400,
        timeout_s=420.0,
    )
    print(f"[A2V_PIPELINE] refiner outputs written: {refiner_output_dir}")

    # 7) combine segment outputs -> inter.json -> render final video
    print("[A2V_PIPELINE][8/10] Combining segment outputs -> inter.json")
    inter_path = run_dir / "inter.json"
    final_video = run_dir / "final_video.mp4"
    print("[A2V_PIPELINE][9/10] Rendering final video")
    render_segment_outputs_to_video(
        segment_outputs_dir=refiner_output_dir,
        media_json_path=media_json_path,
        word_map_all_path=word_map_all_path,
        output_inter_path=inter_path,
        output_video_path=final_video,
    )
    print(f"[A2V_PIPELINE][10/10] Done. Final video: {final_video}")

    return {
        "run_dir": str(run_dir),
        "media_json": str(media_json_path),
        "word_timing_map_all": str(word_map_all_path),
        "element_txt": str(element_txt),
        "planner_combined_input": str(planner_input_prompt),
        "planner_output": str(planner_txt_path),
        "refiner_prompt_dir": str(refiner_prompt_dir),
        "refiner_output_dir": str(refiner_output_dir),
        "inter_json": str(inter_path),
        "video": str(final_video),
    }


def _extract_word_map_all(media_json: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return out
    for media_id, block in analysis.items():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        seq = transcript.get("word_timing_map") or transcript.get("words") or []
        if not isinstance(seq, list):
            continue
        items: list[dict[str, Any]] = []
        for row in seq:
            if not isinstance(row, dict):
                continue
            try:
                s = float(row.get("start"))
                e = float(row.get("end"))
            except Exception:
                continue
            t = str(row.get("text", "")).strip()
            if not t:
                continue
            items.append({"text": t, "start": round(s, 3), "end": round(e, 3)})
        if items:
            out[str(media_id)] = items
    return out


def _safe_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (name or "edit"))
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") or "edit"


def _ensure_static_utility_files(static_dir: Path) -> dict[str, Path]:
    static_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "planner_system_prompt": static_dir / "planner_system_prompt.md",
        "planner_output_schema": static_dir / "planner_output_schema.md",
        "refiner_system_prompt": static_dir / "refiner_system_prompt.md",
        "refiner_output_schema": static_dir / "refiner_output_schema.md",
        "media_understanding": static_dir / "media_understanding.md",
    }
    defaults = {
        "planner_system_prompt": (
            "You are a professional video edit planner.\n"
            "Never leave screen empty: if no media is active, keep captions centered and readable.\n"
            "Keep all elements inside canvas and keep decisions timing-accurate.\n"
        ),
        "planner_output_schema": (
            "Return plain text edit plan with sections and segment decisions.\n"
            "Include caption grouping, timings, placements, transitions, and per-segment rationale.\n"
        ),
        "refiner_system_prompt": (
            "You are a precise video layout and timing planner.\n"
            "Return only valid JSON. Keep visuals inside frame and captions readable/synced.\n"
        ),
        "refiner_output_schema": (
            "{\n"
            '  "canvas": {"width":1080,"height":1920,"fps":30,"duration":30.0},\n'
            '  "final_timeline": [],\n'
            '  "caption_plan": {"element_id":"caption_track_1","mode":"phrase_synced"},\n'
            '  "warnings": []\n'
            "}\n"
        ),
        "media_understanding": (
            "# Media Understanding\n"
            "Describe each element type and how it should be used in short-form edits.\n"
        ),
    }
    for key, path in paths.items():
        if not path.exists():
            path.write_text(defaults[key], encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full new A2V flow in one command.")
    parser.add_argument("--edit-name", required=True, help="Name for this edit run folder.")
    parser.add_argument("--captions-file", required=True, help="captions.txt path; media files must be in same folder.")
    parser.add_argument("--instruction", required=True, help="Main user instruction.")
    parser.add_argument("--planner-endpoint", required=True, help="Planner endpoint URL.")
    parser.add_argument("--refiner-endpoint", required=True, help="Refiner endpoint URL.")
    parser.add_argument("--theme", default="", help="Optional user theme instruction.")
    parser.add_argument("--static-dir", default="vasp/utility_files", help="Directory for permanent utility files.")
    parser.add_argument("--output-root", default="output/edits", help="Root directory for per-edit outputs.")
    args = parser.parse_args()

    result = run_new_flow_pipeline(
        edit_name=args.edit_name,
        captions_file=args.captions_file,
        user_instruction=args.instruction,
        planner_endpoint=args.planner_endpoint,
        refiner_endpoint=args.refiner_endpoint,
        user_theme_instruction=(args.theme.strip() or None),
        static_dir=args.static_dir,
        output_root=args.output_root,
    )
    print("[A2V_PIPELINE] Pipeline summary:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
