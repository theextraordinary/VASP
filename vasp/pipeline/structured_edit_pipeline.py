from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from vasp.planner.build_llm1_prompt import build_llm1_prompt
from vasp.planner.current_video_state import build_current_video_state
from vasp.render.json_creator import create_renderer_json
from vasp.styler.build_llm2_prompt import build_llm2_prompt
from vasp.validation.edit_plan_validator import validate_llm1_output


LLM1_OUTPUT_SCHEMA: dict[str, Any] = {
    "edit_decisions": [
        {
            "decision_id": "string",
            "element_id": "string",
            "element_type": "Caption | Image | Video | Audio | Gif | Sfx | Music | Transition | Shape | TextOverlay",
            "action": "place | animate | trim | show | hide | add | remove | transition | emphasize",
            "t_start": 0.0,
            "t_end": 1.0,
            "purpose": "string",
            "reason": "string",
            "depends_on": [],
            "avoid_overlap_with": [],
            "placement_zone": "center | top | bottom | left | right | full_screen | background | custom | none",
            "notes_for_styler": "string",
        }
    ],
    "element_property_table": [
        {
            "element_id": "string",
            "element_type": "string",
            "exists_in_input": True,
            "is_new_element": False,
            "t_start": 0.0,
            "t_end": 1.0,
            "x": 0.0,
            "y": 0.0,
            "width": 0.0,
            "height": 0.0,
            "z_index": 0,
            "role": "background | foreground | caption | audio | effect | decoration",
            "must_not_cover": [],
            "can_be_covered_by": [],
            "sync_reference": "audio_1/caption_1/null",
            "content_reference": "string",
            "behavior": "string",
        }
    ],
    "timeline_summary": [
        {
            "segment_id": "string",
            "t_start": 0.0,
            "t_end": 1.0,
            "what_is_visible": [],
            "what_is_audible": [],
            "main_focus": "string",
        }
    ],
}

LLM2_DEFAULT_STYLE_RULES: dict[str, Any] = {
    "allow_timing_change": False,
    "allow_position_change": False,
    "caption_readability": "high",
    "style_consistency": "high",
}


def run_structured_edit_pipeline(
    user_instruction: str,
    elements: dict[str, Any],
    canvas: dict[str, Any],
    duration: float,
    llm1_client: Callable[[str], str],
    llm2_client: Callable[[str], str],
) -> dict[str, Any]:
    schema = _load_element_capability_schema()
    normalized_elements = _prepare_elements_for_llm1(elements)
    current_state = build_current_video_state(normalized_elements, canvas, duration)

    llm1_prompt = build_llm1_prompt(
        user_instruction=user_instruction,
        elements=normalized_elements,
        element_capability_schema=schema,
        current_video_state=current_state,
        output_schema=LLM1_OUTPUT_SCHEMA,
    )
    raw_llm1 = llm1_client(llm1_prompt)
    llm1_output = _parse_strict_json_object(raw_llm1)
    if llm1_output is None:
        return {
            "success": False,
            "stage": "llm1_parse",
            "errors": ["LLM1 output is not valid JSON object"],
            "raw_llm1_output": raw_llm1,
        }

    _backfill_missing_core_elements(llm1_output, normalized_elements, duration)
    _sanitize_llm1_layout(llm1_output, normalized_elements, canvas, duration)

    validation = validate_llm1_output(llm1_output, schema, current_state)
    if not validation["valid"]:
        return {
            "success": False,
            "stage": "llm1_validation",
            "errors": validation["errors"],
            "warnings": validation.get("warnings", []),
            "raw_llm1_output": raw_llm1,
        }

    llm2_prompt = build_llm2_prompt(
        user_instruction=user_instruction,
        validated_llm1_output=llm1_output,
        element_capability_schema=schema,
        style_rules=LLM2_DEFAULT_STYLE_RULES,
    )
    raw_llm2 = llm2_client(llm2_prompt)
    llm2_output = _parse_strict_json_object(raw_llm2)
    if llm2_output is None:
        return {
            "success": False,
            "stage": "llm2_parse",
            "errors": ["LLM2 output is not valid JSON object"],
            "raw_llm2_output": raw_llm2,
        }
    style_errors = _validate_llm2_output_light(llm2_output, llm1_output)
    if style_errors:
        return {
            "success": False,
            "stage": "llm2_validation",
            "errors": style_errors,
            "raw_llm2_output": raw_llm2,
        }

    renderer_json = create_renderer_json(
        validated_llm1_output=llm1_output,
        llm2_output=llm2_output,
        original_elements=normalized_elements,
        canvas=canvas,
        duration=duration,
    )
    return {"success": True, "renderer_json": renderer_json}


def _load_element_capability_schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "schemas" / "element_capability_schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_strict_json_object(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _validate_llm2_output_light(llm2_output: dict[str, Any], llm1_output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = llm2_output.get("styled_element_table")
    if not isinstance(rows, list):
        return ["styled_element_table must be a list"]
    allowed_ids = {
        str(r.get("element_id"))
        for r in (llm1_output.get("element_property_table") or [])
        if isinstance(r, dict) and r.get("element_id")
    }
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"styled_element_table[{idx}] must be object")
            continue
        eid = str(row.get("element_id", ""))
        if not eid:
            errors.append(f"styled_element_table[{idx}] missing element_id")
        elif eid not in allowed_ids:
            errors.append(f"styled_element_table[{idx}] references unknown element_id '{eid}'")
    return errors


def _prepare_elements_for_llm1(elements: dict[str, Any]) -> dict[str, Any]:
    """Provide ungrouped caption timing atoms to LLM1 and strip grouped caption actions."""
    if not isinstance(elements, dict):
        return {"elements": []}
    out = json.loads(json.dumps(elements))
    for e in out.get("elements", []):
        if not isinstance(e, dict):
            continue
        et = str(e.get("type", "")).lower()
        if et != "caption":
            continue
        props = e.get("properties", {}) if isinstance(e.get("properties"), dict) else {}
        meta = props.get("metadata", {}) if isinstance(props.get("metadata"), dict) else {}
        word_map = props.get("word_timing_map") if isinstance(props.get("word_timing_map"), list) else None
        if word_map is None and isinstance(meta.get("word_timing_map"), list):
            word_map = meta.get("word_timing_map")
        if word_map is None:
            map_path = props.get("mapping_json") or meta.get("mapping_json")
            if isinstance(map_path, str) and map_path.strip():
                try:
                    p = Path(map_path)
                    if p.exists():
                        loaded = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(loaded, list):
                            word_map = loaded
                except Exception:
                    # Keep pipeline deterministic and resilient; validator will flag if missing.
                    pass
        if word_map is not None:
            props["word_timing_map"] = word_map
        # remove grouped captions from actions to force model-side grouping decisions
        e["actions"] = []
        e["properties"] = props
    return out


def _backfill_missing_core_elements(llm1_output: dict[str, Any], elements: dict[str, Any], duration: float) -> None:
    """Ensure caption/audio/image rows exist so downstream creator doesn't lose them."""
    if not isinstance(llm1_output, dict):
        return
    table = llm1_output.get("element_property_table")
    if not isinstance(table, list):
        llm1_output["element_property_table"] = []
        table = llm1_output["element_property_table"]
    existing_ids = {str(r.get("element_id")) for r in table if isinstance(r, dict) and r.get("element_id")}

    for e in elements.get("elements", []):
        if not isinstance(e, dict):
            continue
        eid = str(e.get("element_id", "")).strip()
        if not eid or eid in existing_ids:
            continue
        etype = str(e.get("type", ""))
        timing = e.get("timing", {}) if isinstance(e.get("timing"), dict) else {}
        start = float(timing.get("start", 0.0) or 0.0)
        end = start + max(0.0, float(timing.get("duration", 0.0) or 0.0))
        props = e.get("properties", {}) if isinstance(e.get("properties"), dict) else {}
        tr = props.get("transform", {}) if isinstance(props.get("transform"), dict) else {}
        row = {
            "element_id": eid,
            "element_type": etype,
            "exists_in_input": True,
            "is_new_element": False,
            "t_start": round(start, 3),
            "t_end": round(min(end, duration), 3),
            "x": tr.get("x"),
            "y": tr.get("y"),
            "width": tr.get("width"),
            "height": tr.get("height"),
            "z_index": int(props.get("z_index", e.get("z_index", 0)) or 0),
            "role": "caption" if etype.lower() == "caption" else ("audio" if etype.lower() in {"music", "audio", "sfx"} else "foreground"),
            "must_not_cover": [],
            "can_be_covered_by": [],
            "sync_reference": "audio_1" if etype.lower() == "caption" else None,
            "content_reference": props.get("text"),
            "behavior": "show" if etype.lower() != "music" else "play",
        }
        table.append(row)


def _sanitize_llm1_layout(
    llm1_output: dict[str, Any],
    elements: dict[str, Any],
    canvas: dict[str, Any],
    duration: float,
) -> None:
    """Deterministically clamp impossible layout/timing before validation.

    This keeps strict validation meaningful while avoiding trivial out-of-canvas failures
    from otherwise-good plans.
    """
    table = llm1_output.get("element_property_table")
    if not isinstance(table, list):
        return

    cw = float(canvas.get("width", 1080) or 1080)
    ch = float(canvas.get("height", 1920) or 1920)
    element_index: dict[str, dict[str, Any]] = {
        str(e.get("element_id")): e
        for e in elements.get("elements", [])
        if isinstance(e, dict) and e.get("element_id")
    }
    audio_like = {"audio", "music", "sfx"}
    visual_like = {"image", "video", "gif", "caption", "shape", "textoverlay", "transition"}

    for row in table:
        if not isinstance(row, dict):
            continue
        etype = str(row.get("element_type", "")).strip().lower()
        eid = str(row.get("element_id", "")).strip()
        source_e = element_index.get(eid, {})
        source_props = source_e.get("properties", {}) if isinstance(source_e.get("properties"), dict) else {}
        source_tr = source_props.get("transform", {}) if isinstance(source_props.get("transform"), dict) else {}

        # Timing clamp
        try:
            ts = float(row.get("t_start", 0.0) or 0.0)
        except Exception:
            ts = 0.0
        try:
            te = float(row.get("t_end", ts + 0.001) or (ts + 0.001))
        except Exception:
            te = ts + 0.001
        ts = max(0.0, min(ts, duration))
        te = max(ts + 0.001, min(te, duration))
        row["t_start"] = round(ts, 3)
        row["t_end"] = round(te, 3)

        if etype in audio_like:
            row["x"] = None
            row["y"] = None
            row["width"] = None
            row["height"] = None
            continue

        if etype not in visual_like:
            continue

        def _num(v: Any) -> float | None:
            try:
                if v is None:
                    return None
                return float(v)
            except Exception:
                return None

        w = _num(row.get("width"))
        h = _num(row.get("height"))
        x = _num(row.get("x"))
        y = _num(row.get("y"))

        # Pull sane defaults from source element if missing.
        if w is None:
            w = _num(source_tr.get("width"))
        if h is None:
            h = _num(source_tr.get("height"))
        if x is None:
            x = _num(source_tr.get("x"))
        if y is None:
            y = _num(source_tr.get("y"))

        if w is None and etype in {"image", "video", "gif"}:
            w = cw
        if h is None and etype in {"image", "video", "gif"}:
            h = ch

        if w is not None:
            w = max(1.0, min(w, cw))
        if h is not None:
            h = max(1.0, min(h, ch))

        if x is not None and w is not None:
            x = min(max(0.0, x), cw - w)
        elif x is not None:
            x = min(max(0.0, x), cw)
        if y is not None and h is not None:
            y = min(max(0.0, y), ch - h)
        elif y is not None:
            y = min(max(0.0, y), ch)

        row["x"] = None if x is None else round(x, 3)
        row["y"] = None if y is None else round(y, 3)
        row["width"] = None if w is None else round(w, 3)
        row["height"] = None if h is None else round(h, 3)
