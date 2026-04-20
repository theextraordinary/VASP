from __future__ import annotations

from typing import Any


ALLOWED_ELEMENT_TYPES = {
    "Audio",
    "Caption",
    "Image",
    "Video",
    "Gif",
    "Sfx",
    "Music",
    "Transition",
    "Shape",
    "TextOverlay",
}

AUDIO_ONLY_TYPES = {"Audio", "Sfx", "Music"}
VISUAL_TYPES = {"Caption", "Image", "Video", "Gif", "Shape", "TextOverlay"}


def validate_llm1_output(
    llm1_output: dict[str, Any],
    element_capability_schema: dict[str, Any],
    current_video_state: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(llm1_output, dict):
        return {"valid": False, "errors": ["llm1_output must be an object"], "warnings": [], "fixed_output": None}

    decisions = llm1_output.get("edit_decisions")
    props_table = llm1_output.get("element_property_table")
    summary = llm1_output.get("timeline_summary")
    if not isinstance(decisions, list):
        errors.append("edit_decisions must be a list")
    if not isinstance(props_table, list):
        errors.append("element_property_table must be a list")
    if not isinstance(summary, list):
        errors.append("timeline_summary must be a list")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "fixed_output": None}

    duration = _to_float(current_video_state.get("duration"), 0.0)
    canvas = current_video_state.get("canvas", {}) if isinstance(current_video_state.get("canvas"), dict) else {}
    canvas_w = _to_float(canvas.get("width"), 0.0)
    canvas_h = _to_float(canvas.get("height"), 0.0)
    existing = {
        str(e.get("element_id")): e
        for e in (current_video_state.get("existing_elements") or [])
        if isinstance(e, dict) and e.get("element_id")
    }
    schema_lookup = _build_schema_lookup(element_capability_schema)

    for idx, row in enumerate(props_table):
        if not isinstance(row, dict):
            errors.append(f"element_property_table[{idx}] must be object")
            continue
        _check_required_fields(
            row,
            ("element_id", "element_type", "t_start", "t_end", "z_index"),
            errors,
            f"element_property_table[{idx}]",
        )
        etype = str(row.get("element_type", ""))
        if etype not in ALLOWED_ELEMENT_TYPES:
            errors.append(f"Unknown element_type '{etype}' in element_property_table[{idx}]")
            continue

        validate_timing(row, duration, errors, f"element_property_table[{idx}]")
        validate_layout(row, canvas_w, canvas_h, errors, f"element_property_table[{idx}]")
        validate_class_capability(row, schema_lookup, errors, f"element_property_table[{idx}]")

        if etype == "Caption":
            if not row.get("content_reference") and not row.get("sync_reference"):
                errors.append(f"Caption in element_property_table[{idx}] must have content_reference or sync_reference")
            sync_ref = str(row.get("sync_reference") or "")
            if sync_ref and "/" not in sync_ref and sync_ref.lower() != "null":
                warnings.append(f"Caption sync_reference '{sync_ref}' is not namespaced (audio_id/caption_id).")

    for idx, d in enumerate(decisions):
        if not isinstance(d, dict):
            errors.append(f"edit_decisions[{idx}] must be object")
            continue
        _check_required_fields(
            d,
            ("decision_id", "element_id", "element_type", "action", "t_start", "t_end"),
            errors,
            f"edit_decisions[{idx}]",
        )
        etype = str(d.get("element_type", ""))
        if etype not in ALLOWED_ELEMENT_TYPES:
            errors.append(f"Unknown element_type '{etype}' in edit_decisions[{idx}]")
            continue
        validate_timing(d, duration, errors, f"edit_decisions[{idx}]")
        validate_class_capability(d, schema_lookup, errors, f"edit_decisions[{idx}]")

    validate_overlaps(props_table, errors, warnings)
    _validate_must_not_cover(props_table, errors)
    _validate_black_gaps(props_table, duration, errors, warnings)
    _validate_caption_coverage(props_table, errors)
    _validate_sync_reference_exists(props_table, existing, warnings)
    _validate_caption_group_timing_against_whisper(props_table, existing, errors, warnings)

    return {"valid": not errors, "errors": errors, "warnings": warnings, "fixed_output": None}


def boxes_overlap(box1: list[float], box2: list[float]) -> bool:
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)


def time_overlap(start1: float, end1: float, start2: float, end2: float) -> bool:
    return start1 < end2 and start2 < end1


def get_schema_for_element_type(element_type: str, schema_lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return schema_lookup.get(element_type)


def validate_timing(row: dict[str, Any], duration: float, errors: list[str], ctx: str) -> None:
    start = _to_float(row.get("t_start"), -1.0)
    end = _to_float(row.get("t_end"), -1.0)
    if start < 0:
        errors.append(f"{ctx}: t_start must be >= 0")
    if end <= start:
        errors.append(f"{ctx}: t_end must be > t_start")
    if duration > 0 and end > duration:
        errors.append(f"{ctx}: t_end exceeds video duration ({duration})")


def validate_layout(row: dict[str, Any], canvas_w: float, canvas_h: float, errors: list[str], ctx: str) -> None:
    etype = str(row.get("element_type", ""))
    x, y = row.get("x"), row.get("y")
    w, h = row.get("width"), row.get("height")

    if etype in AUDIO_ONLY_TYPES:
        if any(v is not None for v in (x, y, w, h)):
            errors.append(f"{ctx}: audio-only element must not define x/y/width/height")
        return

    if etype in VISUAL_TYPES:
        if all(v is not None for v in (x, y, w, h)):
            xf, yf, wf, hf = _to_float(x, -1), _to_float(y, -1), _to_float(w, -1), _to_float(h, -1)
            if xf < 0 or yf < 0:
                errors.append(f"{ctx}: visual element starts outside canvas")
            if canvas_w > 0 and xf + wf > canvas_w:
                errors.append(f"{ctx}: visual element exceeds canvas width")
            if canvas_h > 0 and yf + hf > canvas_h:
                errors.append(f"{ctx}: visual element exceeds canvas height")


def validate_class_capability(
    row: dict[str, Any],
    schema_lookup: dict[str, dict[str, Any]],
    errors: list[str],
    ctx: str,
) -> None:
    etype = str(row.get("element_type", ""))
    schema = get_schema_for_element_type(etype, schema_lookup)
    if not schema:
        errors.append(f"{ctx}: no capability schema for {etype}")
        return

    allowed_props = set(schema.get("allowed_properties", []))
    required_props = set(schema.get("required_properties", []))
    for req in required_props:
        if req in ("start_time", "end_time"):
            continue
        if row.get(req) is None:
            errors.append(f"{ctx}: missing required property '{req}' for {etype}")

    # Map generic planner keys into capability keys for compatibility.
    key_map = {"t_start": "start_time", "t_end": "end_time"}
    for key in row.keys():
        mapped = key_map.get(key, key)
        if mapped in {"element_type"}:
            continue
        if mapped not in allowed_props and key not in {
            "action",
            "x",
            "y",
            "width",
            "height",
            "decision_id",
            "purpose",
            "reason",
            "depends_on",
            "avoid_overlap_with",
            "placement_zone",
            "notes_for_styler",
            "exists_in_input",
            "is_new_element",
            "must_not_cover",
            "can_be_covered_by",
            "sync_reference",
            "content_reference",
            "behavior",
            "role",
            "z_index",
        }:
            errors.append(f"{ctx}: property '{key}' not allowed for {etype}")

    action = str(row.get("action", row.get("behavior", "")))
    if action:
        if action in set(schema.get("forbidden_behaviors", [])):
            errors.append(f"{ctx}: action/behavior '{action}' is forbidden for {etype}")


def validate_overlaps(
    props_table: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> None:
    for i in range(len(props_table)):
        a = props_table[i]
        if not isinstance(a, dict):
            continue
        if str(a.get("element_type", "")) in AUDIO_ONLY_TYPES:
            continue
        if not _has_box(a):
            continue
        a_box = _box(a)
        for j in range(i + 1, len(props_table)):
            b = props_table[j]
            if not isinstance(b, dict):
                continue
            if str(b.get("element_type", "")) in AUDIO_ONLY_TYPES:
                continue
            if not _has_box(b):
                continue
            if not time_overlap(_to_float(a.get("t_start"), 0), _to_float(a.get("t_end"), 0), _to_float(b.get("t_start"), 0), _to_float(b.get("t_end"), 0)):
                continue
            if boxes_overlap(a_box, _box(b)):
                a_type = str(a.get("element_type", ""))
                b_type = str(b.get("element_type", ""))
                if "Caption" in {a_type, b_type}:
                    cap = a if a_type == "Caption" else b
                    other = b if cap is a else a
                    if _to_float(other.get("z_index"), 0) > _to_float(cap.get("z_index"), 0):
                        errors.append(
                            f"Caption overlap violation: '{cap.get('element_id')}' covered by '{other.get('element_id')}' with higher z_index"
                        )
                    else:
                        warnings.append(
                            f"Caption overlap detected between '{a.get('element_id')}' and '{b.get('element_id')}'"
                        )


def _validate_must_not_cover(props_table: list[dict[str, Any]], errors: list[str]) -> None:
    by_id = {str(e.get("element_id")): e for e in props_table if isinstance(e, dict) and e.get("element_id")}
    for e in props_table:
        if not isinstance(e, dict) or not _has_box(e):
            continue
        forbidden = e.get("must_not_cover") or []
        if not isinstance(forbidden, list):
            continue
        for target_id in forbidden:
            t = by_id.get(str(target_id))
            if not t or not _has_box(t):
                continue
            if time_overlap(_to_float(e.get("t_start"), 0), _to_float(e.get("t_end"), 0), _to_float(t.get("t_start"), 0), _to_float(t.get("t_end"), 0)) and boxes_overlap(_box(e), _box(t)):
                errors.append(f"must_not_cover violation: '{e.get('element_id')}' overlaps '{target_id}'")


def _validate_black_gaps(props_table: list[dict[str, Any]], duration: float, errors: list[str], warnings: list[str]) -> None:
    if duration <= 0:
        return
    bg = [
        e
        for e in props_table
        if isinstance(e, dict)
        and str(e.get("role", "")).lower() == "background"
        and str(e.get("element_type", "")) in {"Image", "Video"}
    ]
    if not bg:
        warnings.append("No background visual element declared; cannot guarantee black-gap avoidance.")
        return
    intervals = sorted((_to_float(e.get("t_start"), 0), _to_float(e.get("t_end"), 0)) for e in bg)
    cursor = 0.0
    for s, e in intervals:
        if s > cursor + 1e-3:
            errors.append(f"Background gap detected: {round(cursor,3)}-{round(s,3)}")
        cursor = max(cursor, e)
    if cursor < duration - 1e-3:
        errors.append(f"Background gap detected: {round(cursor,3)}-{round(duration,3)}")


def _validate_caption_coverage(props_table: list[dict[str, Any]], errors: list[str]) -> None:
    captions = [e for e in props_table if isinstance(e, dict) and str(e.get("element_type", "")) == "Caption" and _has_box(e)]
    visuals = [
        e
        for e in props_table
        if isinstance(e, dict)
        and str(e.get("element_type", "")) in VISUAL_TYPES
        and str(e.get("element_type", "")) != "Caption"
        and _has_box(e)
    ]
    for c in captions:
        for v in visuals:
            if not time_overlap(_to_float(c.get("t_start"), 0), _to_float(c.get("t_end"), 0), _to_float(v.get("t_start"), 0), _to_float(v.get("t_end"), 0)):
                continue
            if boxes_overlap(_box(c), _box(v)) and _to_float(v.get("z_index"), 0) > _to_float(c.get("z_index"), 0):
                errors.append(f"Caption '{c.get('element_id')}' is covered by '{v.get('element_id')}'")


def _validate_sync_reference_exists(props_table: list[dict[str, Any]], existing: dict[str, dict[str, Any]], warnings: list[str]) -> None:
    for e in props_table:
        if not isinstance(e, dict):
            continue
        sync_ref = str(e.get("sync_reference") or "")
        if not sync_ref or sync_ref.lower() == "null":
            continue
        # accept ids or namespaced values like audio_1/caption_track_1
        parts = [p for p in sync_ref.split("/") if p]
        if parts and parts[0] not in existing and len(parts) == 1:
            warnings.append(f"sync_reference '{sync_ref}' not present in current_video_state")


def _validate_caption_group_timing_against_whisper(
    props_table: list[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> None:
    caption_rows = [r for r in props_table if isinstance(r, dict) and str(r.get("element_type", "")) == "Caption"]
    if not caption_rows:
        return
    # find first caption source with whisper map
    source = None
    for e in existing.values():
        if str(e.get("element_type", "")).lower() == "caption" and isinstance(e.get("word_timing_map"), list) and e.get("word_timing_map"):
            source = e
            break
    if source is None:
        warnings.append("No caption word_timing_map found in current_video_state; skipped strict caption timing match.")
        return

    words = [w for w in source.get("word_timing_map", []) if isinstance(w, dict)]
    if not words:
        warnings.append("Empty caption word_timing_map in current_video_state; skipped strict caption timing match.")
        return

    norm_words = [_norm_token(str(w.get("text", ""))) for w in words]
    cursor = 0
    for idx, row in enumerate(sorted(caption_rows, key=lambda x: _to_float(x.get("t_start"), 0.0))):
        text = str(row.get("content_reference") or "").strip()
        if not text:
            warnings.append(f"Caption row '{row.get('element_id')}' has empty content_reference; cannot timing-validate.")
            continue
        tokens = [_norm_token(t) for t in text.split() if _norm_token(t)]
        if not tokens:
            warnings.append(f"Caption row '{row.get('element_id')}' has no valid tokens; cannot timing-validate.")
            continue

        match = _find_contiguous_tokens(norm_words, tokens, cursor)
        if match is None:
            errors.append(f"Caption row '{row.get('element_id')}' content_reference does not map to whisper word sequence.")
            continue
        s_i, e_i = match
        cursor = e_i + 1
        expected_start = _to_float(words[s_i].get("start"), -1.0)
        expected_end = _to_float(words[e_i].get("end"), -1.0)
        got_start = _to_float(row.get("t_start"), -1.0)
        got_end = _to_float(row.get("t_end"), -1.0)
        if abs(got_start - expected_start) > 0.08:
            errors.append(
                f"Caption timing mismatch for '{row.get('element_id')}' (group {idx+1}): "
                f"t_start={got_start} expected={expected_start} (first word start)."
            )
        if abs(got_end - expected_end) > 0.08:
            errors.append(
                f"Caption timing mismatch for '{row.get('element_id')}' (group {idx+1}): "
                f"t_end={got_end} expected={expected_end} (last word end)."
            )


def _norm_token(token: str) -> str:
    token = token.strip().lower()
    return "".join(ch for ch in token if ch.isalnum() or ch == "'")


def _find_contiguous_tokens(hay: list[str], needle: list[str], cursor: int) -> tuple[int, int] | None:
    if not needle:
        return None
    for i in range(max(0, cursor), len(hay) - len(needle) + 1):
        if hay[i : i + len(needle)] == needle:
            return i, i + len(needle) - 1
    return None


def _build_schema_lookup(capability_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = capability_schema.get("classes", []) if isinstance(capability_schema, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("class_name", "")).strip()
        if name:
            out[name] = r
    return out


def _has_box(e: dict[str, Any]) -> bool:
    return all(e.get(k) is not None for k in ("x", "y", "width", "height"))


def _box(e: dict[str, Any]) -> list[float]:
    return [
        _to_float(e.get("x"), 0.0),
        _to_float(e.get("y"), 0.0),
        _to_float(e.get("width"), 0.0),
        _to_float(e.get("height"), 0.0),
    ]


def _check_required_fields(row: dict[str, Any], fields: tuple[str, ...], errors: list[str], ctx: str) -> None:
    for f in fields:
        if f not in row:
            errors.append(f"{ctx}: missing required field '{f}'")


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
