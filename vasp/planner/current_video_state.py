from __future__ import annotations

from typing import Any


def build_current_video_state(elements: dict[str, Any], canvas: dict[str, Any], duration: float) -> dict[str, Any]:
    """Build a deterministic snapshot of existing timeline occupancy.

    This intentionally keeps logic simple and predictable for prompt context.
    """
    width = int(float(canvas.get("width", 1080)))
    height = int(float(canvas.get("height", 1920)))
    dur = float(duration)

    raw_elements = elements.get("elements", []) if isinstance(elements, dict) else []
    existing_elements: list[dict[str, Any]] = []
    occupied_regions: list[dict[str, Any]] = []

    for e in raw_elements:
        if not isinstance(e, dict):
            continue
        props = e.get("properties", {}) if isinstance(e.get("properties"), dict) else {}
        timing = e.get("timing", {}) if isinstance(e.get("timing"), dict) else {}
        transform = props.get("transform", {}) if isinstance(props.get("transform"), dict) else {}
        start = _to_float(timing.get("start"), 0.0)
        end = start + max(0.0, _to_float(timing.get("duration"), 0.0))
        x = _to_float(transform.get("x"), 0.0)
        y = _to_float(transform.get("y"), 0.0)
        w = _to_float(transform.get("width"), _to_float(transform.get("w"), 0.0))
        h = _to_float(transform.get("height"), _to_float(transform.get("h"), 0.0))
        z = int(_to_float(props.get("z_index"), _to_float(e.get("z_index"), 0.0)))

        item = {
            "element_id": str(e.get("element_id", "")),
            "element_type": str(e.get("type", props.get("type", ""))),
            "t_start": round(start, 3),
            "t_end": round(min(end, dur), 3),
            "x": x if w > 0 else None,
            "y": y if h > 0 else None,
            "width": w if w > 0 else None,
            "height": h if h > 0 else None,
            "z_index": z,
        }
        if str(item["element_type"]).lower() == "caption":
            item["word_timing_map"] = _extract_word_timing_map(e)
            transcript = _extract_transcript(e)
            if transcript:
                item["transcript"] = transcript
        existing_elements.append(item)

        if w > 0 and h > 0:
            occupied_regions.append(
                {
                    "t_start": round(start, 3),
                    "t_end": round(min(end, dur), 3),
                    "regions": [
                        {
                            "element_id": item["element_id"],
                            "bbox": [x, y, w, h],
                            "z_index": z,
                        }
                    ],
                }
            )

    return {
        "canvas": {"width": width, "height": height},
        "duration": round(dur, 3),
        "existing_elements": existing_elements,
        "occupied_regions_by_time": occupied_regions,
    }


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_word_timing_map(element: dict[str, Any]) -> list[dict[str, Any]]:
    props = element.get("properties", {}) if isinstance(element.get("properties"), dict) else {}
    meta = props.get("metadata", {}) if isinstance(props.get("metadata"), dict) else {}
    candidates = [
        props.get("word_timing_map"),
        meta.get("word_timing_map"),
    ]
    for c in candidates:
        if isinstance(c, list):
            out = []
            for w in c:
                if not isinstance(w, dict):
                    continue
                out.append(
                    {
                        "text": str(w.get("text", "")),
                        "start": round(_to_float(w.get("start"), 0.0), 3),
                        "end": round(_to_float(w.get("end"), 0.0), 3),
                    }
                )
            if out:
                return out
    return []


def _extract_transcript(element: dict[str, Any]) -> str:
    props = element.get("properties", {}) if isinstance(element.get("properties"), dict) else {}
    meta = props.get("metadata", {}) if isinstance(props.get("metadata"), dict) else {}
    if isinstance(props.get("text"), str) and props.get("text"):
        return str(props.get("text"))
    trans = meta.get("transcript")
    if isinstance(trans, dict) and isinstance(trans.get("full_text"), str):
        return str(trans.get("full_text"))
    return ""
