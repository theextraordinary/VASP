from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from vasp.animation.catalog import list_animation_presets
from vasp.design.render_catalog import render_design_catalog_text


SEGMENT_REFINER_OUTPUT_SCHEMA: dict[str, Any] = {
    "canvas": {"width": 1080, "height": 1920, "fps": 30, "duration": 30.035},
    "final_timeline": [
        {
            "element_id": "string",
            "type": "audio | video | image | gif | sticker | caption",
            "role": "main_audio | main_visual | supporting_visual | accent | caption",
            "t_start": 0.0,
            "t_end": 0.0,
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
            "z_index": 1,
            "opacity": 1.0,
            "fit": "cover | contain | none",
            "transition_in": {"type": "none | fade | cut | zoom | slide | pop", "duration": 0.0},
            "transition_out": {"type": "none | fade | cut | zoom | slide | pop", "duration": 0.0},
            "animation": {"type": "none | slow_zoom_in | slow_zoom_out | float | pulse | shake", "intensity": "low | medium | high"},
            "caption_safe": True,
            "reason": "short reason",
        }
    ],
    "caption_plan": {
        "element_id": "caption_track_1",
        "mode": "phrase_synced",
        "placement": {"x": 90, "y": 1450, "width": 900, "height": 300, "z_index": 10},
        "sync_source": "word_timing_map",
        "style_notes": "large readable captions with highlighted spoken phrase",
    },
    "warnings": [],
}


def build_segmented_refiner_prompts(
    *,
    system_prompt_path: str | Path,
    planner_output_path: str | Path,
    media_json_path: str | Path,
    output_schema_path: str | Path = "output/refiner_output_schema.md",
    output_dir: str | Path = "output/refiner_segment_prompts",
) -> list[Path]:
    """Create one refiner input prompt per planner segment."""
    system_prompt = Path(system_prompt_path).read_text(encoding="utf-8-sig").strip()
    planner_text = Path(planner_output_path).read_text(encoding="utf-8")
    media_json = json.loads(Path(media_json_path).read_text(encoding="utf-8"))

    planner_json = _try_parse_json(planner_text)
    video_summary = _extract_video_summary(planner_json, planner_text)
    asset_understanding = _extract_asset_understanding(planner_json, media_json, planner_text)
    segments = _extract_segments(planner_json, planner_text)
    if not segments:
        segments = [{"segment_id": "segment_1", "t_start": 0.0, "t_end": _extract_duration(media_json)}]

    caption_maps = _extract_caption_time_mappings(media_json)
    allowed = _allowed_design_and_animations()
    canvas = _extract_canvas(media_json)
    schema_text = _load_output_schema_text(output_schema_path)

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for i, seg in enumerate(segments, start=1):
        seg_start = _rf(seg.get("t_start"))
        seg_end = _rf(seg.get("t_end"))
        prompt = (
            f"{system_prompt}\n\n"
            f"{json.dumps(video_summary, ensure_ascii=False, indent=2)}\n\n"
            f"{json.dumps(asset_understanding, ensure_ascii=False, indent=2)}\n\n"
            f"{json.dumps(caption_maps, ensure_ascii=False, indent=2)}\n\n"
            f"{json.dumps(allowed, ensure_ascii=False, indent=2)}\n\n"
            f"{json.dumps(seg, ensure_ascii=False, indent=2)}\n\n"
            f"This segment is strictly from t_start={seg_start} to t_end={seg_end}. "
            "All final_timeline actions in your output must stay inside this interval.\n\n"
            f"{schema_text}\n"
        )
        out_path = out_root / f"refiner_segment_prompt_{i:02d}.txt"
        out_path.write_text(prompt, encoding="utf-8")
        written.append(out_path)

    index_path = out_root / "refiner_segment_prompt_index.json"
    index_path.write_text(
        json.dumps(
            {
                "count": len(written),
                "files": [str(p).replace("\\", "/") for p in written],
                "planner_output_path": str(Path(planner_output_path)).replace("\\", "/"),
                "media_json_path": str(Path(media_json_path)).replace("\\", "/"),
                "output_schema_path": str(Path(output_schema_path)).replace("\\", "/"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return written


def _try_parse_json(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # Best-effort extraction from fenced markdown blocks
    m = re.search(r"```json\s*(\{.*\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        m = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1).strip())
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_video_summary(planner_json: dict[str, Any] | None, planner_text: str) -> dict[str, Any]:
    if isinstance(planner_json, dict):
        if isinstance(planner_json.get("video_summary"), dict):
            return planner_json["video_summary"]
        if isinstance(planner_json.get("video_understanding"), dict):
            return planner_json["video_understanding"]
    summary_only = _extract_section_text(planner_text, "VIDEO SUMMARY", "ASSET UNDERSTANDING")
    if summary_only:
        return {"summary": "Derived from planner text", "raw_summary": summary_only}
    # Best-effort extraction from loose JSON text.
    loose = _extract_top_object_block(planner_text, "video_summary")
    if isinstance(loose, dict):
        return loose
    return {"summary": "Derived from planner text", "raw_summary": ""}


def _extract_asset_understanding(
    planner_json: dict[str, Any] | None,
    media_json: dict[str, Any],
    planner_text: str,
) -> list[dict[str, Any]]:
    if isinstance(planner_json, dict) and isinstance(planner_json.get("asset_understanding"), list):
        return [x for x in planner_json["asset_understanding"] if isinstance(x, dict)]
    loose_assets = _extract_asset_understanding_loose(planner_text=planner_text)
    if loose_assets:
        return loose_assets
    inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    out: list[dict[str, Any]] = []
    for item in inputs:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "element_id": item.get("id"),
                "type": item.get("media_type"),
                "represents": item.get("about"),
                "best_use": item.get("aim"),
                "usefulness": "medium",
                "reason": "derived from media input",
            }
        )
    return out


def _extract_segments(planner_json: dict[str, Any] | None, planner_text: str) -> list[dict[str, Any]]:
    if isinstance(planner_json, dict):
        if isinstance(planner_json.get("segments"), list):
            return [_normalize_segment_obj(x, i + 1) for i, x in enumerate(planner_json["segments"]) if isinstance(x, dict)]
        if isinstance(planner_json.get("timeline_plan"), list):
            return [_normalize_segment_obj(x, i + 1) for i, x in enumerate(planner_json["timeline_plan"]) if isinstance(x, dict)]
    # Fallback parser for plain text with "SEGMENT N" blocks.
    lines = planner_text.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"^\s*SEGMENT\s+\d+", ln, flags=re.IGNORECASE)]
    if not starts:
        loose = _extract_segments_loose(planner_text)
        return loose
    starts.append(len(lines))
    out: list[dict[str, Any]] = []
    for idx in range(len(starts) - 1):
        block_lines = lines[starts[idx] : starts[idx + 1]]
        parsed = _parse_segment_block(block_lines, idx + 1)
        out.append(parsed)
    return out


def _normalize_segment_obj(seg: dict[str, Any], index: int) -> dict[str, Any]:
    out = dict(seg)
    sid = str(out.get("segment_id", "")).strip()
    if not sid:
        sid = f"segment_{index}"
    out["segment_id"] = sid

    ts = _coerce_float(out.get("t_start"))
    te = _coerce_float(out.get("t_end"))

    # Support "time": "x to y" or "x-y"
    time_val = out.get("time")
    if (ts is None or te is None) and isinstance(time_val, str):
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:to|[-–])\s*([0-9]+(?:\.[0-9]+)?)", time_val, flags=re.IGNORECASE)
        if m:
            ts = float(m.group(1))
            te = float(m.group(2))

    # Support segment_id itself containing time "x to y"
    if (ts is None or te is None) and isinstance(sid, str):
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:to|[-–])\s*([0-9]+(?:\.[0-9]+)?)", sid, flags=re.IGNORECASE)
        if m:
            ts = float(m.group(1))
            te = float(m.group(2))

    out["t_start"] = ts if ts is not None else 0.0
    out["t_end"] = te if te is not None else 0.0
    out.pop("raw_text", None)
    return out


def _coerce_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _extract_caption_time_mappings(media_json: dict[str, Any]) -> dict[str, Any]:
    grouped: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if isinstance(analysis, dict):
        for block in analysis.values():
            if not isinstance(block, dict):
                continue
            transcript = block.get("transcript")
            if not isinstance(transcript, dict):
                continue
            g = transcript.get("caption_groups")
            if isinstance(g, list):
                for i, row in enumerate(g):
                    if not isinstance(row, dict):
                        continue
                    grouped.append(
                        {
                            "index": i,
                            "text": row.get("text"),
                            "start": _rf(row.get("start")),
                            "end": _rf(row.get("end")),
                        }
                    )
            w = transcript.get("words")
            if isinstance(w, list):
                for i, row in enumerate(w):
                    if not isinstance(row, dict):
                        continue
                    words.append(
                        {
                            "index": i,
                            "text": row.get("text"),
                            "start": _rf(row.get("start")),
                            "end": _rf(row.get("end")),
                        }
                    )
            if grouped or words:
                break
    return {
        "word_timing_map": words,
        "grouped_caption_map": grouped,
        "preferred_sync_source": "word_timing_map" if words else "grouped_caption_map",
    }


def _allowed_design_and_animations() -> dict[str, Any]:
    return {
        "animations": list_animation_presets(),
        "design_catalog_text": render_design_catalog_text(),
    }


def _extract_canvas(media_json: dict[str, Any]) -> dict[str, Any]:
    video = media_json.get("video", {}) if isinstance(media_json, dict) else {}
    size = video.get("size", {}) if isinstance(video, dict) else {}
    return {
        "width": int(float(size.get("width", 1080) or 1080)),
        "height": int(float(size.get("height", 1920) or 1920)),
        "fps": int(float(video.get("fps", 30) or 30)),
        "duration": _extract_duration(media_json),
    }


def _extract_duration(media_json: dict[str, Any]) -> float:
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    max_d = 0.0
    if isinstance(probe, dict):
        for row in probe.values():
            if not isinstance(row, dict):
                continue
            try:
                max_d = max(max_d, float(row.get("duration") or 0.0))
            except Exception:
                pass
    return round(max_d, 3) if max_d > 0 else 30.0


def _find_num(text: str, key: str) -> float | None:
    m = re.search(rf"{re.escape(key)}\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _extract_top_object_block(text: str, key: str) -> dict[str, Any] | None:
    m = re.search(rf'"{re.escape(key)}"\s*:\s*\{{', text)
    if not m:
        return None
    start = m.end() - 1
    obj_text = _extract_brace_block(text, start)
    if not obj_text:
        return None
    try:
        val = json.loads(obj_text)
        return val if isinstance(val, dict) else None
    except Exception:
        return None


def _extract_asset_understanding_loose(planner_text: str) -> list[dict[str, Any]]:
    m = re.search(r'"asset_understanding"\s*:\s*\[', planner_text)
    if not m:
        return []
    start = m.end() - 1
    arr_text = _extract_bracket_block(planner_text, start)
    if not arr_text:
        return []
    try:
        arr = json.loads(arr_text)
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    return [x for x in arr if isinstance(x, dict)]


def _extract_segments_loose(planner_text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(r'"segment_id"\s*:\s*"([^"]+)"', planner_text):
        # find nearest enclosing object start
        i = m.start()
        obj_start = planner_text.rfind("{", 0, i)
        if obj_start < 0:
            continue
        obj_text = _extract_brace_block(planner_text, obj_start)
        if not obj_text:
            continue
        try:
            seg = json.loads(obj_text)
        except Exception:
            continue
        if not isinstance(seg, dict):
            continue
        seg_n = _normalize_segment_obj(seg, len(out) + 1)
        if seg_n.get("t_end", 0.0) > seg_n.get("t_start", 0.0):
            out.append(seg_n)
    # de-dup by segment_id preserving order
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for s in out:
        sid = str(s.get("segment_id", ""))
        if sid in seen:
            continue
        seen.add(sid)
        uniq.append(s)
    return uniq


def _extract_brace_block(text: str, start_idx: int) -> str | None:
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start_idx, len(text)):
        ch = text[i]
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
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_idx : i + 1]
    return None


def _extract_bracket_block(text: str, start_idx: int) -> str | None:
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "[":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start_idx, len(text)):
        ch = text[i]
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
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start_idx : i + 1]
    return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _parse_segment_block(block_lines: list[str], segment_index: int) -> dict[str, Any]:
    header = block_lines[0].strip() if block_lines else f"SEGMENT {segment_index}"
    seg: dict[str, Any] = {"segment_id": f"segment_{segment_index}"}
    m = re.match(r"^\s*SEGMENT\s+(\d+)", header, flags=re.IGNORECASE)
    if m:
        seg["segment_id"] = f"segment_{m.group(1)}"

    parsed_time_start: float | None = None
    parsed_time_end: float | None = None

    for ln in block_lines[1:]:
        line = ln.strip()
        if not line:
            continue
        kv = re.match(r"^-?\s*([A-Za-z0-9_ /-]+)\s*:\s*(.+)$", line)
        if not kv:
            continue
        key_raw = kv.group(1).strip().lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        val = kv.group(2).strip()
        seg[key_raw] = val

        if key_raw == "time":
            # Supports "0.031-6.451" or "0.031 - 6.451"
            tm = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)\s*$", val)
            if tm:
                parsed_time_start = float(tm.group(1))
                parsed_time_end = float(tm.group(2))
            else:
                tto = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*to\s*([0-9]+(?:\.[0-9]+)?)\s*$", val, flags=re.IGNORECASE)
                if tto:
                    parsed_time_start = float(tto.group(1))
                    parsed_time_end = float(tto.group(2))
        elif key_raw in {"t_start", "start", "segment_start"}:
            try:
                parsed_time_start = float(val)
            except Exception:
                pass
        elif key_raw in {"t_end", "end", "segment_end"}:
            try:
                parsed_time_end = float(val)
            except Exception:
                pass
        elif key_raw in {"segment_id", "timeline", "window", "segment_window"}:
            tto = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*(?:to|[-–])\s*([0-9]+(?:\.[0-9]+)?)",
                val,
                flags=re.IGNORECASE,
            )
            if tto:
                parsed_time_start = float(tto.group(1))
                parsed_time_end = float(tto.group(2))

    seg["t_start"] = parsed_time_start if parsed_time_start is not None else 0.0
    seg["t_end"] = parsed_time_end if parsed_time_end is not None else 0.0
    return seg


def _extract_section_text(text: str, start_heading: str, end_heading: str) -> str:
    lines = text.splitlines()
    start_idx = None
    end_idx = None
    start_pat = re.compile(rf"^\s*{re.escape(start_heading)}\s*:?\s*$", flags=re.IGNORECASE)
    end_pat = re.compile(rf"^\s*{re.escape(end_heading)}\s*:?\s*$", flags=re.IGNORECASE)
    for i, ln in enumerate(lines):
        if start_idx is None and start_pat.match(ln):
            start_idx = i + 1
            continue
        if start_idx is not None and end_pat.match(ln):
            end_idx = i
            break
    if start_idx is None:
        return ""
    block = lines[start_idx:end_idx] if end_idx is not None else lines[start_idx:]
    return "\n".join(block).strip()


def _load_output_schema_text(path_like: str | Path) -> str:
    p = Path(path_like)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff").strip()
    return json.dumps(SEGMENT_REFINER_OUTPUT_SCHEMA, ensure_ascii=False, indent=2)


def _rf(v: Any) -> float:
    try:
        return round(float(v), 3)
    except Exception:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build per-segment refiner prompts from planner output + media.json")
    parser.add_argument("--system-prompt", default="output/refiner_system_prompt_v1.txt")
    parser.add_argument("--planner-output", required=True)
    parser.add_argument("--media-json", default="output/media.json")
    parser.add_argument("--output-schema", default="output/refiner_output_schema.md")
    parser.add_argument("--output-dir", default="output/refiner_segment_prompts")
    args = parser.parse_args()

    paths = build_segmented_refiner_prompts(
        system_prompt_path=args.system_prompt,
        planner_output_path=args.planner_output,
        media_json_path=args.media_json,
        output_schema_path=args.output_schema,
        output_dir=args.output_dir,
    )
    print(json.dumps({"count": len(paths), "first": str(paths[0]) if paths else None}, indent=2))


if __name__ == "__main__":
    main()
