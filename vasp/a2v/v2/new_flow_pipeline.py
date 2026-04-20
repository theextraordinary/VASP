from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from vasp.a2v.v2.creativity_policy import CREATIVITY_LEVELS, get_creativity_policy
from vasp.core.serializer_v3 import write_element3_txt_from_media_json
from vasp.media_reader.from_captions import create_media_json_from_captions_file
from vasp.planner.cli_combined import call_planner_endpoint
from vasp.planner.combined_prompt_builder import generate_combined_planner_input_prompt
from vasp.planner.planner_validator import (
    parse_planner_json,
    validate_and_fix_planner_output,
    validate_planner_output,
)
from vasp.refiner.segment_inference_runner import run_refiner_for_segment_prompts
from vasp.refiner.segment_output_renderer import render_segment_outputs_to_video
from vasp.refiner.segment_prompt_builder import build_segmented_refiner_prompts

MAX_PLANNER_ATTEMPTS = 5


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
    creativity: int = 2,
) -> dict[str, str]:
    creativity_policy = get_creativity_policy(creativity)
    static_paths = _ensure_static_utility_files(Path(static_dir))
    run_dir = Path(output_root) / _safe_name(edit_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[A2V_PIPELINE] Run dir: {run_dir}")
    print(f"[A2V_PIPELINE] Creativity: {creativity}")
    creativity_policy_path = run_dir / "creativity_policy.json"
    creativity_policy_path.write_text(json.dumps(creativity_policy, ensure_ascii=False, indent=2), encoding="utf-8")

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
    media_context_txt = media_context_generator(
        media_json=media_json,
        output_path=run_dir / "media_context.txt",
    )
    print(f"[A2V_PIPELINE] media context text written: {media_context_txt}")
    planner_context_txt = _build_planner_context_with_media_understanding(
        media_context_path=media_context_txt,
        media_understanding_path=static_paths["media_understanding"],
        output_path=run_dir / "planner_context.txt",
    )
    print(f"[A2V_PIPELINE] planner context text written: {planner_context_txt}")

    # 3) planner combined prompt
    print("[A2V_PIPELINE][4/10] Building planner combined prompt")
    planner_input_prompt = generate_combined_planner_input_prompt(
        system_prompt_path=static_paths["planner_system_prompt"],
        transcript=None,  # auto-extracted from media.json
        user_instruction=user_instruction,
        user_specific_instruction=user_theme_instruction,
        element3_path=planner_context_txt,
        output_schema_path=static_paths["planner_output_schema"],
        output_prompt_path=run_dir / "planner_combined_input.txt",
        media_json_path=media_json_path,
    )

    # 4) planner endpoint -> planner output
    print("[A2V_PIPELINE][5/10] Calling planner endpoint")
    planner_txt_path = run_dir / "planner_output.txt"
    planner_meta_path = run_dir / "planner_output.meta.json"
    _call_planner_with_validation_retries(
        endpoint=planner_endpoint,
        prompt_path=planner_input_prompt,
        output_text_path=planner_txt_path,
        output_meta_path=planner_meta_path,
        media_json=media_json,
        temperature=0.1,
        max_tokens=2400,
        timeout_s=420.0,
        max_attempts=MAX_PLANNER_ATTEMPTS,
    )
    print(f"[A2V_PIPELINE] planner output written: {planner_txt_path}")

    # 5) per-segment refiner prompts
    print("[A2V_PIPELINE][6/10] Building per-segment refiner prompts")
    refiner_prompt_dir = run_dir / "refiner_segment_prompts"
    build_segmented_refiner_prompts(
        system_prompt_path=static_paths["refiner_system_prompt"],
        planner_output_path=planner_txt_path,
        media_json_path=media_json_path,
        element_context_path=element_txt,
        output_schema_path=static_paths["refiner_output_schema"],
        output_dir=refiner_prompt_dir,
        creativity=creativity,
    )

    # 6) per-segment refiner outputs
    print("[A2V_PIPELINE][7/10] Calling refiner endpoint per segment")
    refiner_output_dir = run_dir / "refiner_segment_outputs"
    print("[A2V_PIPELINE][REFINER_VALIDATE] Skipped. Using first refiner output per segment.")
    refiner_report = run_refiner_for_segment_prompts(
        prompts_dir=refiner_prompt_dir,
        endpoint=refiner_endpoint,
        output_dir=refiner_output_dir,
        planner_output_path=planner_txt_path,
        temperature=0.1,
        max_tokens=2400,
        timeout_s=420.0,
        max_attempts=1,
        enable_validation=False,
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
        "media_context_txt": str(media_context_txt),
        "planner_context_txt": str(planner_context_txt),
        "planner_combined_input": str(planner_input_prompt),
        "planner_output": str(planner_txt_path),
        "creativity_policy": str(creativity_policy_path),
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


def media_context_generator(*, media_json: dict[str, Any], output_path: Path) -> Path:
    media_inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})

    lines: list[str] = []
    lines.append("MEDIA CONTEXT")
    lines.append("Use this as media inventory. Keep timing decisions from caption groups only.")
    lines.append("")

    for row in media_inputs:
        if not isinstance(row, dict):
            continue
        media_id = str(row.get("id", "")).strip()
        media_type = str(row.get("media_type", "")).strip().lower()
        if not media_id:
            continue
        if "caption" in media_type:
            continue
        etype = media_type or "-"
        aim = str(row.get("aim", "")).strip() or "-"
        about = str(row.get("about", "")).strip() or "-"
        lines.append(f"{media_id} | type: {etype} | aim: {aim} | about: {about}")

    lines.append("")
    lines.append("CAPTION GROUP TO TIME MAPPING")

    groups = _extract_grouped_caption_map(media_json)
    for g in groups:
        try:
            idx = int(g.get("index"))
            ts = float(g.get("start"))
            te = float(g.get("end"))
        except Exception:
            continue
        txt = str(g.get("text", "")).strip()
        lines.append(f"{idx}: {ts:.3f} -> {te:.3f} | {txt}")

    lines.append("")
    lines.append("TIMING RULE")
    lines.append("Use only caption-group boundary times listed above.")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path


def _build_planner_context_with_media_understanding(
    *,
    media_context_path: Path,
    media_understanding_path: Path,
    output_path: Path,
) -> Path:
    media_context_text = media_context_path.read_text(encoding="utf-8").strip()
    media_understanding_text = media_understanding_path.read_text(encoding="utf-8").strip()
    merged = (
        "MEDIA UNDERSTANDING REFERENCE\n"
        f"{media_understanding_text}\n\n"
        f"{media_context_text}\n"
    )
    output_path.write_text(merged, encoding="utf-8")
    return output_path


def _call_planner_with_validation_retries(
    *,
    endpoint: str,
    prompt_path: Path,
    output_text_path: Path,
    output_meta_path: Path,
    media_json: dict[str, Any],
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    max_attempts: int = MAX_PLANNER_ATTEMPTS,
) -> tuple[Path, Path]:
    # Planner validation is intentionally skipped; keep first model output only.
    print("[A2V_PIPELINE][PLANNER_VALIDATE] Skipped. Using first planner output as-is.")
    call_planner_endpoint(
        endpoint=endpoint,
        prompt_path=prompt_path,
        output_text_path=output_text_path,
        output_meta_path=output_meta_path,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )
    return output_text_path, output_meta_path


def _extract_grouped_caption_map(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return []
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        groups = transcript.get("caption_groups")
        if not isinstance(groups, list):
            continue
        out: list[dict[str, Any]] = []
        for i, row in enumerate(groups):
            if not isinstance(row, dict):
                continue
            try:
                s = float(row.get("start"))
                e = float(row.get("end"))
            except Exception:
                continue
            out.append(
                {
                    "index": i,
                    "text": str(row.get("text", "")).strip(),
                    "start": round(s, 3),
                    "end": round(e, 3),
                }
            )
        if out:
            return out
    return []


def _build_asset_registry(media_json: dict[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    if isinstance(inputs, list):
        for row in inputs:
            if not isinstance(row, dict):
                continue
            eid = str(row.get("id", "")).strip()
            if not eid:
                continue
            mtype = str(row.get("media_type", "")).strip().lower()
            out[eid] = {"type": _normalize_asset_type(mtype)}
    # Ensure canonical caption track exists for planner constraints.
    out.setdefault("caption_track_1", {"type": "caption"})
    return out


def _normalize_asset_type(media_type: str) -> str:
    mt = media_type.lower().strip()
    if "audio" in mt:
        return "audio"
    if "caption" in mt:
        return "caption"
    if "sticker" in mt:
        return "sticker"
    if "gif" in mt:
        return "gif"
    if "video" in mt:
        return "video"
    if "image" in mt:
        return "image"
    return mt or "unknown"


def _write_planner_debug_artifacts(
    *,
    raw_obj: dict[str, Any],
    fixed_obj: dict[str, Any],
    report: dict[str, Any],
    output_text_path: Path,
) -> None:
    debug_dir = Path("output/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "planner_raw.json").write_text(json.dumps(raw_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug_dir / "planner_fixed.json").write_text(json.dumps(fixed_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug_dir / "planner_validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    run_debug_dir = output_text_path.parent / "debug"
    run_debug_dir.mkdir(parents=True, exist_ok=True)
    (run_debug_dir / "planner_raw.json").write_text(json.dumps(raw_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_debug_dir / "planner_fixed.json").write_text(json.dumps(fixed_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_debug_dir / "planner_validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_planner_repair_prompt(base_prompt: str, bad_output: str, errors: list[str]) -> str:
    repair_rules = (
        "\n\n### VALIDATION FEEDBACK (MUST FIX)\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\n### REPAIR INSTRUCTIONS\n"
        + "- Return ONLY valid JSON object (no markdown fences, no commentary).\n"
        + "- Keep the SAME top-level structure as originally requested.\n"
        + "- Do not drop required fields.\n"
        + "- Ensure each segment has all required fields and valid timing.\n"
        + "- Complete any truncated/incomplete trailing segment objects.\n"
    )
    return (
        base_prompt
        + repair_rules
        + "\n\n### PREVIOUS INVALID OUTPUT (FOR REPAIR ONLY)\n"
        + bad_output
    )


def _build_planner_continuation_prompt(base_prompt: str, partial_output: str) -> str:
    return (
        base_prompt
        + "\n\n### CONTINUATION MODE\n"
        + "Your previous response was truncated mid-JSON.\n"
        + "Continue from EXACTLY where it stopped.\n"
        + "Do not restart from the beginning. Do not wrap in markdown.\n"
        + "Return ONLY the missing continuation text so the combined result becomes one complete valid JSON object.\n"
        + "\n### PARTIAL OUTPUT SO FAR (DO NOT REPEAT FROM START)\n"
        + partial_output
    )


def _should_try_planner_continuation(errors: list[str]) -> bool:
    joined = " ".join(errors).lower()
    truncation_markers = (
        "unterminated string",
        "expecting value",
        "expecting ',' delimiter",
        "unclosed",
        "unexpected end",
    )
    return "invalid_json" in joined and any(marker in joined for marker in truncation_markers)


def _merge_planner_chunks(prefix: str, continuation: str) -> str:
    p = str(prefix or "")
    c = str(continuation or "")
    if not p:
        return c
    if not c:
        return p
    # Trim exact overlap to avoid duplicate tails when model repeats a few chars.
    max_overlap = min(len(p), len(c), 300)
    overlap = 0
    for n in range(max_overlap, 0, -1):
        if p[-n:] == c[:n]:
            overlap = n
            break
    return p + c[overlap:]


def _validate_planner_output_text(text: str) -> dict[str, Any]:
    errors: list[str] = []
    cleaned = str(text or "").strip()
    if not cleaned:
        return {"ok": False, "errors": ["empty response"]}

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return {"ok": False, "errors": [f"invalid_json: {exc.msg}"]}

    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["root must be a JSON object"]}

    required_top = ("video_summary", "asset_understanding", "segments")
    for key in required_top:
        if key not in obj:
            errors.append(f"missing top-level key '{key}'")

    segments = obj.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append("segments must be a non-empty array")
    else:
        prev_end: float | None = None
        for i, seg in enumerate(segments):
            ctx = f"segments[{i}]"
            if not isinstance(seg, dict):
                errors.append(f"{ctx} must be an object")
                continue
            required_seg = (
                "segment_id",
                "t_start",
                "t_end",
                "caption_indices",
                "spoken_text",
                "segment_purpose",
                "visual_candidates",
                "caption_instruction",
                "transition_intent",
            )
            for key in required_seg:
                if key not in seg:
                    errors.append(f"{ctx} missing '{key}'")
            try:
                t_start = float(seg.get("t_start"))
                t_end = float(seg.get("t_end"))
                if t_end <= t_start:
                    errors.append(f"{ctx} has invalid time window")
                if prev_end is not None and t_start + 1e-6 < prev_end:
                    errors.append(f"{ctx} starts before previous segment ended")
                prev_end = t_end
            except (TypeError, ValueError):
                errors.append(f"{ctx} has non-numeric t_start/t_end")

    return {"ok": len(errors) == 0, "errors": errors}


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
    parser.add_argument("--creativity", type=int, default=2, choices=CREATIVITY_LEVELS)
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
        creativity=args.creativity,
    )
    print("[A2V_PIPELINE] Pipeline summary:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
