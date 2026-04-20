from __future__ import annotations

import json
from typing import Any


def validate_planner_output(
    planner_output: dict[str, Any] | str,
    *,
    elements: dict[str, Any],
    video_duration: float,
    transcript_exists: bool = True,
) -> dict[str, Any]:
    """Validate logic-only planner output against structural and safety rules."""
    errors: list[str] = []
    warnings: list[str] = []

    obj = _parse_obj(planner_output)
    if obj is None:
        return {"valid": False, "errors": ["output is not valid JSON object"], "warnings": []}

    required = [
        "video_understanding",
        "asset_understanding",
        "timeline_plan",
        "element_actions",
        "needs_user_input",
        "creative_suggestions",
    ]
    for key in required:
        if key not in obj:
            errors.append(f"missing required key: {key}")

    known_ids, type_by_id, caption_ids, audio_ids, visual_ids = _collect_element_sets(elements)
    duration = float(video_duration)

    timeline = obj.get("timeline_plan")
    if not isinstance(timeline, list):
        errors.append("timeline_plan must be a list")
        timeline = []
    for i, seg in enumerate(timeline):
        if not isinstance(seg, dict):
            errors.append(f"timeline_plan[{i}] must be an object")
            continue
        ts = _f(seg.get("t_start"))
        te = _f(seg.get("t_end"))
        if ts is None or te is None:
            errors.append(f"timeline_plan[{i}] missing valid t_start/t_end")
            continue
        if ts < 0:
            errors.append(f"timeline_plan[{i}] t_start must be >= 0")
        if te <= ts:
            errors.append(f"timeline_plan[{i}] t_end must be > t_start")
        if te > duration + 1e-6:
            errors.append(f"timeline_plan[{i}] exceeds video duration ({duration})")

    actions = obj.get("element_actions")
    if not isinstance(actions, list):
        errors.append("element_actions must be a list")
        actions = []

    fullscreen_visuals: list[tuple[float, float, str, int]] = []
    caption_non_skip = 0
    low_use_assets: set[str] = set()
    asset_understanding = obj.get("asset_understanding")
    if isinstance(asset_understanding, list):
        for row in asset_understanding:
            if not isinstance(row, dict):
                continue
            if str(row.get("usefulness", "")).lower() == "low":
                eid = str(row.get("element_id", "")).strip()
                if eid:
                    low_use_assets.add(eid)

    has_skip_action_for_low: set[str] = set()
    for i, act in enumerate(actions):
        if not isinstance(act, dict):
            errors.append(f"element_actions[{i}] must be an object")
            continue
        eid = str(act.get("element_id", "")).strip()
        action = str(act.get("action", "")).strip().lower()
        role = str(act.get("role", "")).strip().lower()
        zone = str(act.get("placement_zone", "")).strip().lower()
        ts = _f(act.get("t_start"))
        te = _f(act.get("t_end"))

        if not eid:
            errors.append(f"element_actions[{i}] missing element_id")
            continue
        if action != "add" and eid not in known_ids:
            errors.append(f"element_actions[{i}] unknown element_id '{eid}'")
        if ts is None or te is None:
            errors.append(f"element_actions[{i}] missing valid t_start/t_end")
            continue
        if ts < 0 or te <= ts:
            errors.append(f"element_actions[{i}] invalid time window")
        if te > duration + 1e-6:
            errors.append(f"element_actions[{i}] exceeds video duration ({duration})")

        if eid in audio_ids and zone not in {"none", ""}:
            errors.append(f"element_actions[{i}] audio element '{eid}' must use placement_zone=none")

        if eid in caption_ids and action != "skip":
            caption_non_skip += 1

        if eid in visual_ids and action in {"show", "place"}:
            avoid = act.get("avoid_covering")
            if not isinstance(avoid, list) or not any(str(x) in caption_ids for x in avoid):
                errors.append(f"element_actions[{i}] visual action must avoid covering captions")

            if zone == "full_screen":
                fullscreen_visuals.append((ts, te, eid, i))

            full_span = duration > 0 and (te - ts) >= 0.95 * duration
            if full_span and role != "background":
                errors.append(
                    f"element_actions[{i}] visual '{eid}' spans almost full video but role is not background"
                )

        if eid in low_use_assets and action == "skip":
            has_skip_action_for_low.add(eid)

    if transcript_exists and caption_ids and caption_non_skip == 0:
        errors.append("captions are skipped/missing while transcript exists")

    # full-screen overlap check
    for a_idx in range(len(fullscreen_visuals)):
        a = fullscreen_visuals[a_idx]
        for b_idx in range(a_idx + 1, len(fullscreen_visuals)):
            b = fullscreen_visuals[b_idx]
            if _time_overlap(a[0], a[1], b[0], b[1]):
                errors.append(
                    f"multiple full-screen visuals overlap in time: '{a[2]}' and '{b[2]}'"
                )

    # mismatch handling: low-use assets should be skipped or explicitly discussed
    suggestions = obj.get("creative_suggestions")
    has_suggestions = isinstance(suggestions, list) and len(suggestions) > 0
    unresolved_low = sorted(eid for eid in low_use_assets if eid not in has_skip_action_for_low)
    if unresolved_low and not has_suggestions:
        warnings.append(
            "media/transcript mismatch may be unresolved: low-use assets not skipped and no creative_suggestions provided"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def _parse_obj(payload: dict[str, Any] | str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, str):
        return None
    text = payload.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _collect_element_sets(
    elements: dict[str, Any],
) -> tuple[set[str], dict[str, str], set[str], set[str], set[str]]:
    known_ids: set[str] = set()
    type_by_id: dict[str, str] = {}
    caption_ids: set[str] = set()
    audio_ids: set[str] = set()
    visual_ids: set[str] = set()

    for e in elements.get("elements", []) if isinstance(elements, dict) else []:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("element_id", "")).strip()
        props = e.get("properties", {}) if isinstance(e.get("properties"), dict) else {}
        etype = str(props.get("type", e.get("type", ""))).strip().lower()
        if not eid:
            continue
        known_ids.add(eid)
        type_by_id[eid] = etype
        if etype == "caption":
            caption_ids.add(eid)
        if etype in {"audio", "music", "sfx"}:
            audio_ids.add(eid)
        if etype in {"image", "video", "gif"}:
            visual_ids.add(eid)

    return known_ids, type_by_id, caption_ids, audio_ids, visual_ids


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _time_overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1

