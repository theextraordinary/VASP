from __future__ import annotations

from collections import defaultdict
from typing import Any


def create_renderer_json(
    validated_llm1_output: dict[str, Any],
    llm2_output: dict[str, Any],
    original_elements: dict[str, Any],
    canvas: dict[str, Any],
    duration: float,
) -> dict[str, Any]:
    """Merge original data + validated plan + style table into renderer-ready JSON."""
    table = validated_llm1_output.get("element_property_table", [])
    style_rows = llm2_output.get("styled_element_table", []) if isinstance(llm2_output, dict) else []
    style_by_id = {str(r.get("element_id")): r for r in style_rows if isinstance(r, dict) and r.get("element_id")}
    original_by_id = _index_original_elements(original_elements)

    elements_out: list[dict[str, Any]] = []
    tracks = defaultdict(list)
    for row in table:
        if not isinstance(row, dict):
            continue
        element_id = str(row.get("element_id", "")).strip()
        if not element_id:
            continue
        element_type = str(row.get("element_type", ""))
        original = original_by_id.get(element_id, {})
        style_row = style_by_id.get(element_id, {})

        source = _pick_source(original)
        text = row.get("content_reference")
        if text is None and isinstance(original.get("properties"), dict):
            text = original.get("properties", {}).get("text")

        merged_style = _build_style(style_row)
        merged_animation = _build_animation(style_row)
        merged_audio = _build_audio(style_row, row, element_type)

        out = {
            "id": element_id,
            "type": element_type,
            "source": source,
            "text": text,
            "start": _to_float(row.get("t_start"), 0.0),
            "end": _to_float(row.get("t_end"), _to_float(row.get("t_start"), 0.0)),
            "x": _nullable_float(row.get("x")),
            "y": _nullable_float(row.get("y")),
            "width": _nullable_float(row.get("width")),
            "height": _nullable_float(row.get("height")),
            "z_index": int(_to_float(row.get("z_index"), 0.0)),
            "style": merged_style,
            "animation": merged_animation,
            "audio": merged_audio,
            "metadata": {
                "role": row.get("role"),
                "sync_reference": row.get("sync_reference"),
                "must_not_cover": row.get("must_not_cover", []),
                "can_be_covered_by": row.get("can_be_covered_by", []),
                "behavior": row.get("behavior"),
            },
        }
        elements_out.append(out)

        track_type = _track_type_for_element(element_type, row.get("role"))
        tracks[track_type].append(out)

    track_list = []
    for idx, (t_type, items) in enumerate(tracks.items(), start=1):
        track_list.append({"track_id": f"track_{idx}", "type": t_type, "elements": [e["id"] for e in items]})

    return {
        "canvas": {
            "width": int(_to_float(canvas.get("width"), 1080)),
            "height": int(_to_float(canvas.get("height"), 1920)),
            "fps": int(_to_float(canvas.get("fps"), 30)),
            "duration": float(duration),
        },
        "tracks": track_list,
        "elements": elements_out,
    }


def _index_original_elements(original_elements: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = original_elements.get("elements", []) if isinstance(original_elements, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("element_id"):
            out[str(r["element_id"])] = r
    return out


def _pick_source(original: dict[str, Any]) -> str | None:
    props = original.get("properties", {}) if isinstance(original.get("properties"), dict) else {}
    src = props.get("source_uri")
    if src is None:
        src = original.get("source")
    return str(src) if src is not None else None


def _build_style(style_row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "font_family",
        "font_size",
        "font_weight",
        "text_color",
        "highlight_color",
        "background_color",
        "opacity",
        "border_radius",
        "shadow",
    )
    out = {k: style_row.get(k) for k in keys if k in style_row and style_row.get(k) is not None}
    out.update(style_row.get("extra_renderer_props", {}) if isinstance(style_row.get("extra_renderer_props"), dict) else {})
    return out


def _build_animation(style_row: dict[str, Any]) -> dict[str, Any]:
    keys = ("animation_in", "animation_out", "animation_during", "transition", "crop", "scale", "rotation")
    return {k: style_row.get(k) for k in keys if k in style_row and style_row.get(k) is not None}


def _build_audio(style_row: dict[str, Any], row: dict[str, Any], element_type: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if element_type in {"Audio", "Sfx", "Music"}:
        out["volume"] = _to_float(style_row.get("volume", 1.0), 1.0)
    elif style_row.get("volume") is not None:
        out["volume"] = _to_float(style_row.get("volume"), 1.0)
    if row.get("sync_reference") is not None:
        out["sync_reference"] = row.get("sync_reference")
    return out


def _track_type_for_element(element_type: str, role: Any) -> str:
    role_s = str(role or "").lower()
    if element_type in {"Audio", "Sfx", "Music"} or role_s == "audio":
        return "audio"
    if element_type == "Caption" or role_s == "caption":
        return "caption"
    if element_type in {"Transition", "Shape"} or role_s in {"effect", "decoration"}:
        return "effect"
    return "visual"


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

