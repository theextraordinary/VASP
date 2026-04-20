from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from vasp.a2v.v2.creativity_policy import CREATIVITY_LEVELS, get_creativity_policy
from vasp.a2v.v2.pipeline_v2_utils import (
    caption_boundary_set,
    caption_groups_for_segment,
    extract_audio_duration,
    extract_grouped_caption_map,
    extract_main_audio_id,
    extract_main_transcript,
    extract_media_inventory,
    extract_whisper_segments,
    fallback_segments_from_caption_groups,
    load_media_json,
    to_float,
)
from vasp.media_reader.from_captions import create_media_json_from_captions_file
from vasp.refiner.segment_output_renderer import render_segment_outputs_to_video
from vasp.a2v.v2.renderer_v2 import render_inter_v2


def _post_llm(endpoint: str, prompt: str, temperature: float, max_tokens: int, timeout_s: float = 420.0) -> str:
    resp = httpx.post(
        endpoint,
        json={"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens},
        timeout=timeout_s,
    )
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict):
        return str(payload.get("response", "")).strip()
    return str(payload).strip()


def _extract_json(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    if "```json" in t.lower():
        s = t.lower().find("```json")
        e = t.find("```", s + 7)
        if s >= 0 and e > s:
            chunk = t[s + 7 : e].strip()
            try:
                obj = json.loads(chunk)
                return obj if isinstance(obj, dict) else None
            except Exception:
                pass
    # balanced object
    start = t.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    begin = -1
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                begin = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and begin >= 0:
                chunk = t[begin : i + 1]
                try:
                    obj = json.loads(chunk)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


def _asset_role_for(media_type: str) -> str:
    mt = (media_type or "").lower()
    if "audio" in mt or mt in {"music", "sfx"}:
        return "main_audio"
    if "caption" in mt:
        return "caption"
    if "gif" in mt or "sticker" in mt:
        return "visual_candidate"
    if "image" in mt or "video" in mt:
        return "supporting_visual"
    return "supporting_visual"


def _build_asset_understanding_fallback(media_inventory: list[dict[str, Any]]) -> str:
    lines = ["ASSET UNDERSTANDING"]
    for m in media_inventory:
        eid = m.get("element_id")
        mt = str(m.get("type", ""))
        role = _asset_role_for(mt)
        lines.append(
            f"- element_id: {eid}\n"
            f"  type: {mt}\n"
            f"  about: {m.get('about','')}\n"
            f"  aim: {m.get('aim','')}\n"
            f"  semantic_tags: []\n"
            f"  best_caption_keywords: []\n"
            f"  suggested_role: {role}\n"
            f"  usefulness: medium\n"
            f"  when_to_use: use when transcript matches about/aim\n"
            f"  when_not_to_use: do not use when topic mismatches"
        )
    return "\n".join(lines).strip() + "\n"


def _planner_segment_valid(
    obj: dict[str, Any],
    *,
    media_visual_ids: set[str],
    banned_ids: set[str],
    seg_start: float,
    seg_end: float,
    local_boundary: set[float],
) -> tuple[bool, list[str]]:
    errs: list[str] = []
    vt = obj.get("visual_timeline")
    if not isinstance(vt, list):
        errs.append("visual_timeline missing or not list")
        return False, errs
    seen: set[tuple[str, float, float]] = set()
    for row in vt:
        if not isinstance(row, dict):
            errs.append("visual_timeline item not object")
            continue
        eid = str(row.get("element_id", "")).strip()
        if not eid:
            errs.append("visual item missing element_id")
            continue
        if eid in banned_ids:
            errs.append(f"visual contains banned id {eid}")
        if eid not in media_visual_ids:
            errs.append(f"visual id not in media inventory {eid}")
        th = row.get("time_hint")
        if not isinstance(th, dict):
            errs.append(f"{eid} missing time_hint")
            continue
        s = round(to_float(th.get("start"), -1), 3)
        e = round(to_float(th.get("end"), -1), 3)
        if s < 0 or e <= s:
            errs.append(f"{eid} invalid time_hint")
            continue
        if s < seg_start - 1e-3 or e > seg_end + 1e-3:
            errs.append(f"{eid} time_hint outside segment")
        if local_boundary and (s not in local_boundary or e not in local_boundary):
            errs.append(f"{eid} time_hint not on caption boundary")
        key = (eid, s, e)
        if key in seen:
            errs.append(f"duplicate visual item {eid}:{s}-{e}")
        seen.add(key)
    return len(errs) == 0, errs


def _fallback_segment_planner_output(segment: dict[str, Any], local_groups: list[dict[str, Any]], errs: list[str]) -> dict[str, Any]:
    return {
        "segment_id": segment.get("segment_id"),
        "t_start": round(to_float(segment.get("t_start"), 0.0), 3),
        "t_end": round(to_float(segment.get("t_end"), 0.0), 3),
        "caption_indices": [int(g.get("index")) for g in local_groups if isinstance(g.get("index"), int)],
        "spoken_text": str(segment.get("spoken_text", "")).strip(),
        "visual_timeline": [],
        "caption_instruction": "No visual selected; captions should carry this segment.",
        "warnings": [f"planner_segment_fallback: {e}" for e in errs] if errs else ["planner_segment_fallback"],
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _extract_element_ids_from_text(text: str) -> list[str]:
    import re

    ids = re.findall(r"\bmedia_\d+\b|\bcaption_track_\d+\b", text or "")
    out: list[str] = []
    seen: set[str] = set()
    for eid in ids:
        if eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


def _segment_asset_context(
    *,
    planner_segment_text: str,
    media_inventory: list[dict[str, Any]],
    asset_understanding_text: str,
) -> tuple[list[dict[str, Any]], str]:
    mapped_ids = set(_extract_element_ids_from_text(planner_segment_text))
    mapped_inventory = [m for m in media_inventory if str(m.get("element_id")) in mapped_ids]

    # Keep it robust even when asset_understanding is plain text:
    # include only lines that mention mapped ids plus a few following lines.
    lines = asset_understanding_text.splitlines()
    selected: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        hit = None
        for eid in mapped_ids:
            if eid in line:
                hit = eid
                break
        if hit:
            selected.append(line)
            # capture a short local block under this line
            j = i + 1
            extra = 0
            while j < len(lines) and extra < 8:
                nxt = lines[j]
                if any(mid in nxt for mid in mapped_ids) and extra > 0:
                    break
                selected.append(nxt)
                j += 1
                extra += 1
            i = j
            continue
        i += 1
    mapped_asset_text = "\n".join(selected).strip()
    return mapped_inventory, mapped_asset_text


def run_new_flow_pipeline_v2(
    *,
    edit_name: str,
    captions_file: str | Path,
    user_instruction: str,
    planner_url: str,
    refiner_url: str,
    output_dir: str | Path = "output/edits",
    skip_refiner: bool = False,
    skip_render: bool = False,
    max_planner_tokens: int = 1200,
    max_refiner_tokens: int = 1600,
    temperature: float = 0.0,
    creativity: int = 2,
) -> dict[str, str]:
    creativity_policy = get_creativity_policy(creativity)
    out_root = Path(output_dir) / _safe_name(edit_name)
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"[A2V_V2] creativity={creativity}")
    creativity_policy_path = out_root / "creativity_policy.json"
    creativity_policy_path.write_text(json.dumps(creativity_policy, ensure_ascii=False, indent=2), encoding="utf-8")
    media_json_path = out_root / "media.json"

    # Keep v2 flow similar to old flow: build media.json from captions input first.
    media_json_obj = create_media_json_from_captions_file(
        captions_file_path=captions_file,
        output_media_json_path=media_json_path,
        instruction=user_instruction,
    )
    media_json_path.write_text(json.dumps(media_json_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[A2V_V2] media.json written: {media_json_path}")

    planner_root = out_root / "planner_v2"
    planner_inputs_dir = planner_root / "segment_inputs"
    planner_outputs_dir = planner_root / "segment_outputs"
    refiner_root = out_root / "refiner_v2"
    refiner_inputs_dir = refiner_root / "segment_inputs"
    refiner_outputs_dir = refiner_root / "segment_outputs"
    for d in [planner_root, planner_inputs_dir, planner_outputs_dir, refiner_root, refiner_inputs_dir, refiner_outputs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    media_json = load_media_json(media_json_path)
    media_inventory = extract_media_inventory(media_json)
    grouped = extract_grouped_caption_map(media_json)
    transcript = extract_main_transcript(media_json)
    main_audio_id = extract_main_audio_id(media_json)
    audio_duration = extract_audio_duration(media_json, main_audio_id)
    whisper_segments = extract_whisper_segments(media_json)
    if not whisper_segments:
        whisper_segments = fallback_segments_from_caption_groups(grouped, max_groups_per_segment=4)
    print(f"[A2V_V2] segments={len(whisper_segments)} grouped_captions={len(grouped)}")

    planner_ctx = (
        "USER INSTRUCTION\n"
        f"{user_instruction}\n\n"
        "MEDIA INVENTORY\n"
        f"{json.dumps(media_inventory, ensure_ascii=False, indent=2)}\n\n"
        "FULL TRANSCRIPT\n"
        f"{transcript}\n\n"
        "FULL CAPTION TIMING MAP\n"
        f"{json.dumps(grouped, ensure_ascii=False, indent=2)}\n\n"
        "WHISPER SEGMENTS\n"
        f"{json.dumps(whisper_segments, ensure_ascii=False, indent=2)}\n\n"
        f"MAIN_AUDIO_ID: {main_audio_id}\n"
        f"AUDIO_DURATION: {audio_duration}\n"
    )
    (planner_root / "planner_context.txt").write_text(planner_ctx, encoding="utf-8")

    utility_dir = Path("vasp/utility_files")
    planner_system = _read_text(utility_dir / "planner_system_prompt_v2.md")
    planner_schema = _read_text(utility_dir / "planner_output_schema_v2.md")
    refiner_system = _read_text(Path("vasp/utility_files/refiner_system_prompt.md"))
    refiner_schema = _read_text(Path("vasp/utility_files/refiner_output_schema.md"))
    if not refiner_system:
        refiner_system = "Return valid JSON with visual_timeline and optional caption_render_policy."

    # Asset understanding call (single planner call).
    asset_understanding_input = (
        "SYSTEM PROMPT:\n"
        "You are an expert A2V asset analyst.\n"
        "Generate detailed, accurate asset understanding from the provided transcript, media inventory, and user instruction.\n"
        "Return plain text only.\n"
        "Be precise, avoid hallucinations, and ground decisions in provided metadata and transcript context.\n\n"
        "Required fields per asset:\n"
        "- element_id\n"
        "- type\n"
        "- about\n"
        "- aim\n"
        "- semantic_tags\n"
        "- best_caption_keywords\n"
        "- suggested_role\n"
        "- usefulness\n"
        "- when_to_use\n"
        "- when_not_to_use\n\n"
        "Role mapping rules:\n"
        "- audio -> main_audio\n"
        "- caption_track -> caption\n"
        "- video/image -> supporting_visual\n"
        "- gif/sticker -> visual_candidate\n"
        "- never map caption as supporting_visual\n\n"
        f"USER INSTRUCTION:\n{user_instruction}\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        f"MEDIA INVENTORY:\n{json.dumps(media_inventory, ensure_ascii=False, indent=2)}\n"
    )
    au_input_path = planner_root / "asset_understanding_input.txt"
    au_input_path.write_text(asset_understanding_input, encoding="utf-8")
    try:
        au_resp = _post_llm(planner_url, asset_understanding_input, temperature, max_planner_tokens)
        if not au_resp.strip():
            raise ValueError("empty asset understanding")
    except Exception as exc:
        print(f"[A2V_V2][WARN] asset understanding call failed, using fallback: {exc}")
        au_resp = _build_asset_understanding_fallback(media_inventory)
    au_path = planner_root / "asset_understanding.txt"
    au_path.write_text(au_resp, encoding="utf-8")

    media_visual_ids = {str(x.get("element_id")) for x in media_inventory if "audio" not in str(x.get("type", "")) and "caption" not in str(x.get("type", ""))}
    banned_ids = {str(x.get("element_id")) for x in media_inventory if ("audio" in str(x.get("type", "")) or "caption" in str(x.get("type", "")))}
    planned_outputs: list[Path] = []

    for i, seg in enumerate(whisper_segments):
        sid = f"{i:03d}"
        local_groups = caption_groups_for_segment(grouped, seg)
        seg_prompt = (
            f"{planner_system}\n\n{planner_schema}\n\n"
            f"USER INSTRUCTION:\n{user_instruction}\n\n"
            f"ASSET UNDERSTANDING:\n{au_resp}\n\n"
            f"SEGMENT:\n{json.dumps(seg, ensure_ascii=False, indent=2)}\n\n"
            f"LOCAL GROUPED CAPTION MAP (ONLY THIS SEGMENT):\n{json.dumps(local_groups, ensure_ascii=False, indent=2)}\n\n"
            f"MEDIA INVENTORY:\n{json.dumps(media_inventory, ensure_ascii=False, indent=2)}\n"
        )
        in_path = planner_inputs_dir / f"planner_input_segment_{sid}.txt"
        out_path = planner_outputs_dir / f"planner_output_segment_{sid}.txt"
        in_path.write_text(seg_prompt, encoding="utf-8")

        raw = _post_llm(planner_url, seg_prompt, temperature, max_planner_tokens)
        out_path.write_text(raw, encoding="utf-8")
        # Validation disabled by request; keep first planner output as-is.
        ok = True
        planned_outputs.append(out_path)
        print(f"[A2V_V2][PLANNER] segment={sid} validation=skipped")

    # Refiner per segment
    refiner_outputs: list[Path] = []
    if not skip_refiner:
        for i, seg in enumerate(whisper_segments):
            sid = f"{i:03d}"
            planner_seg_path = planner_outputs_dir / f"planner_output_segment_{sid}.txt"
            planner_seg_text = planner_seg_path.read_text(encoding="utf-8")
            local_groups = caption_groups_for_segment(grouped, seg)
            mapped_inventory, mapped_asset_text = _segment_asset_context(
                planner_segment_text=planner_seg_text,
                media_inventory=media_inventory,
                asset_understanding_text=au_resp,
            )
            refiner_input = (
                f"{refiner_system}\n\n"
                f"CREATIVITY POLICY:\n{creativity_policy['rules_text']}\n\n"
                f"{refiner_schema}\n\n"
                f"USER INSTRUCTION:\n{user_instruction}\n\n"
                f"ASSET UNDERSTANDING (SEGMENT-MAPPED):\n{mapped_asset_text or au_resp}\n\n"
                f"ELEMENT DATA (SEGMENT-MAPPED FROM MEDIA.JSON):\n{json.dumps(mapped_inventory, ensure_ascii=False, indent=2)}\n\n"
                f"LOCAL CAPTION GROUPS:\n{json.dumps(local_groups, ensure_ascii=False, indent=2)}\n\n"
                # Keep refiner input structure unchanged; replace segment input block content
                # with the corresponding planner segment output.
                f"SEGMENT INPUT:\n{planner_seg_text}\n\n"
                "SEGMENT CONSTRAINTS:\n"
                f"- t_start={seg.get('t_start')}\n- t_end={seg.get('t_end')}\n"
            )
            rin = refiner_inputs_dir / f"refiner_input_segment_{sid}.txt"
            rout = refiner_outputs_dir / f"refiner_segment_output_{sid}.txt"
            rin.write_text(refiner_input, encoding="utf-8")
            resp = _post_llm(refiner_url, refiner_input, temperature, max_refiner_tokens)
            rout.write_text(resp, encoding="utf-8")
            refiner_outputs.append(rout)
            print(f"[A2V_V2][REFINER] segment={sid} done")
    else:
        print("[A2V_V2] --skip-refiner enabled; using planner segment outputs as refiner outputs")
        for i in range(len(whisper_segments)):
            sid = f"{i:03d}"
            src = planner_outputs_dir / f"planner_output_segment_{sid}.txt"
            dst = refiner_outputs_dir / f"refiner_segment_output_{sid}.txt"
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            refiner_outputs.append(dst)

    # Use old combiner + old renderer path.
    inter_path = out_root / "inter.json"
    final_video_path = out_root / "final_video.mp4"
    render_segment_outputs_to_video(
        segment_outputs_dir=refiner_outputs_dir,
        media_json_path=media_json_path,
        output_inter_path=inter_path,
        output_video_path=final_video_path,
        use_old_renderer=False,
    )
    if skip_render:
        print("[A2V_V2] --skip-render enabled")
    else:
        render_inter_v2(inter_path)

    return {
        "run_dir": str(out_root),
        "media_json": str(media_json_path),
        "planner_context": str(planner_root / "planner_context.txt"),
        "asset_understanding_input": str(au_input_path),
        "asset_understanding": str(au_path),
        "creativity_policy": str(creativity_policy_path),
        "planner_segment_inputs_dir": str(planner_inputs_dir),
        "planner_segment_outputs_dir": str(planner_outputs_dir),
        "refiner_segment_inputs_dir": str(refiner_inputs_dir),
        "refiner_segment_outputs_dir": str(refiner_outputs_dir),
        "inter_json": str(inter_path),
        "final_video": str(final_video_path),
    }


def _safe_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (name or "edit_v2"))
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") or "edit_v2"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run new A2V flow v2 (Whisper-segment driven).")
    parser.add_argument("--edit-name", required=True)
    parser.add_argument("--captions-file", required=True)
    parser.add_argument("--instruction", "--user-instruction", dest="instruction", required=True)
    parser.add_argument("--planner-endpoint", "--planner-url", dest="planner_endpoint", required=True)
    parser.add_argument("--refiner-endpoint", "--refiner-url", dest="refiner_endpoint", required=True)
    parser.add_argument("--output-dir", default="output/edits")
    parser.add_argument("--skip-refiner", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--max-planner-tokens", type=int, default=1200)
    parser.add_argument("--max-refiner-tokens", type=int, default=1600)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--creativity", type=int, default=2, choices=CREATIVITY_LEVELS)
    args = parser.parse_args()

    result = run_new_flow_pipeline_v2(
        edit_name=args.edit_name,
        captions_file=args.captions_file,
        user_instruction=args.instruction,
        planner_url=args.planner_endpoint,
        refiner_url=args.refiner_endpoint,
        output_dir=args.output_dir,
        skip_refiner=bool(args.skip_refiner),
        skip_render=bool(args.skip_render),
        max_planner_tokens=int(args.max_planner_tokens),
        max_refiner_tokens=int(args.max_refiner_tokens),
        temperature=float(args.temperature),
        creativity=int(args.creativity),
    )
    print("[A2V_V2] Pipeline summary:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
