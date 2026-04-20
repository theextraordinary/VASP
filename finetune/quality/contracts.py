from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

PLANNER_REQUIRED_HEADINGS = [
    "EDIT PLAN",
    "Global Style:",
    "Audio Decision:",
    "Caption Style:",
    "Visual Style:",
    "Background Style:",
    "Segmentation Rule:",
    "Segment 1",
    "Time:",
    "Purpose:",
    "Elements Used:",
    "Caption Decision:",
    "Visual Decision:",
    "Animation Decision:",
    "Placement Decision:",
    "Timing Events:",
    "Transition Out:",
    "Engagement Note:",
]

PLANNER_GROUPING_RULE_MARKERS = [
    "1-5 words",
    "group captions",
    "caption group",
    "chunk",
    "sentence boundary",
    "uppercase",
]

PLANNER_TIMING_RULE_MARKERS = [
    "group start = first word start",
    "group end = next group first-word start",
]


@dataclass
class ContractCheck:
    ok: bool
    score: float
    errors: list[str]
    details: dict[str, Any]


def parse_jsonish(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            parsed = json.loads(text[s : e + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def planner_element_ids(text: str) -> set[str]:
    return set(re.findall(r"\b(?:audio|image|caption|music|sfx|gif|video)_[0-9A-Za-z_]+\b", text))


def compact_element_ids(text: str) -> set[str]:
    return set(re.findall(r"element:([0-9A-Za-z_]+)", text))


def check_planner_output(text: str, user_prompt: str = "") -> ContractCheck:
    errors: list[str] = []
    details: dict[str, Any] = {}

    starts_ok = text.lstrip().startswith("EDIT PLAN")
    if not starts_ok:
        errors.append("planner_missing_edit_plan_prefix")

    heading_hits = {h: (h in text) for h in PLANNER_REQUIRED_HEADINGS}
    missing_headings = [h for h, ok in heading_hits.items() if not ok]
    if missing_headings:
        errors.append("planner_missing_headings")
        details["missing_headings"] = missing_headings

    lower = text.lower()
    markers_found = [m for m in PLANNER_GROUPING_RULE_MARKERS if m.lower() in lower]
    if len(markers_found) < 1:
        errors.append("planner_weak_grouping_directive")
    details["grouping_markers_found"] = markers_found

    timing_markers_found = [m for m in PLANNER_TIMING_RULE_MARKERS if m.lower() in lower]
    has_timing_events = ("timing events:" in lower) and ("- time:" in lower)
    if not timing_markers_found and not has_timing_events:
        errors.append("planner_missing_explicit_timing_rule")
    details["timing_markers_found"] = timing_markers_found
    details["has_timing_events_block"] = has_timing_events

    segment_count = len(re.findall(r"\bSegment\s+\d+\b", text))
    if segment_count < 1:
        errors.append("planner_missing_segments")
    details["segment_count"] = segment_count

    if user_prompt:
        compact_ids = compact_element_ids(user_prompt)
        plan_ids = planner_element_ids(text)
        if compact_ids and not plan_ids.issubset(compact_ids):
            errors.append("planner_references_unknown_element_ids")
            details["unknown_planner_ids"] = sorted(plan_ids - compact_ids)
        if compact_ids and not plan_ids:
            errors.append("planner_missing_element_references")

    # Simple weighted score.
    score = 1.0
    if not starts_ok:
        score -= 0.35
    if missing_headings:
        score -= min(0.45, 0.03 * len(missing_headings))
    if "planner_weak_grouping_directive" in errors:
        score -= 0.20
    if "planner_missing_explicit_timing_rule" in errors:
        score -= 0.15
    if "planner_missing_element_references" in errors:
        score -= 0.15
    score = max(0.0, round(score, 4))
    non_fatal = {"planner_weak_grouping_directive"}
    fatal_errors = [e for e in errors if e not in non_fatal]
    details["fatal_errors"] = fatal_errors
    return ContractCheck(ok=not fatal_errors, score=score, errors=errors, details=details)


def check_refiner_inter(inter: dict[str, Any], planner_text: str = "") -> ContractCheck:
    errors: list[str] = []
    details: dict[str, Any] = {}

    if not isinstance(inter, dict):
        return ContractCheck(False, 0.0, ["refiner_not_object"], {})

    video = inter.get("video")
    elements = inter.get("elements")
    if not isinstance(video, dict):
        errors.append("refiner_missing_video")
    if not isinstance(elements, list):
        errors.append("refiner_missing_elements")
        elements = []

    size = video.get("size", {}) if isinstance(video, dict) else {}
    if not isinstance(size, dict) or size.get("width") is None or size.get("height") is None:
        errors.append("refiner_missing_video_size")
    if isinstance(video, dict) and video.get("fps") is None:
        errors.append("refiner_missing_fps")
    if isinstance(video, dict) and not video.get("output_path"):
        errors.append("refiner_missing_output_path")

    width = _to_float(size.get("width"), -1.0) if isinstance(size, dict) else -1.0
    height = _to_float(size.get("height"), -1.0) if isinstance(size, dict) else -1.0
    max_action_end = 0.0

    element_ids: set[str] = set()
    for e in elements:
        if not isinstance(e, dict):
            errors.append("refiner_non_object_element")
            continue
        for key in ("element_id", "type", "timing", "actions", "properties"):
            if key not in e:
                errors.append(f"refiner_element_missing_{key}")
        if e.get("actions") is not None and not isinstance(e.get("actions"), list):
            errors.append("refiner_element_actions_not_list")
        if isinstance(e.get("element_id"), str):
            element_ids.add(e["element_id"])
        elem_type = str(e.get("type", ""))
        actions_any = e.get("actions", []) if isinstance(e.get("actions"), list) else []
        for a in actions_any:
            if not isinstance(a, dict):
                continue
            ts = _to_float(a.get("t_start"), -1.0)
            te = _to_float(a.get("t_end"), -1.0)
            if ts < 0.0:
                errors.append("refiner_action_negative_start")
            if te < ts:
                errors.append("refiner_action_invalid_interval")
            max_action_end = max(max_action_end, te)
            op = str(a.get("op", ""))
            if elem_type in {"music", "sfx"} and op not in {"play", "stop"}:
                errors.append("refiner_audio_invalid_op")
            if elem_type in {"caption", "image", "video", "gif", "sticker", "shape"} and op != "show":
                errors.append("refiner_visual_invalid_op")
        if e.get("element_id") == "caption_track_1":
            actions = e.get("actions", [])
            if not isinstance(actions, list):
                errors.append("refiner_caption_actions_not_list")
            else:
                prev_end = -1e9
                for idx, a in enumerate(actions):
                    if not isinstance(a, dict):
                        errors.append("refiner_caption_action_not_object")
                        continue
                    ts = _to_float(a.get("t_start"), -1.0)
                    te = _to_float(a.get("t_end"), -1.0)
                    if ts > te:
                        errors.append("refiner_caption_action_invalid_interval")
                    if ts < prev_end - 1e-6:
                        errors.append("refiner_caption_actions_overlap")
                    prev_end = max(prev_end, te)
                    params = a.get("params", {}) if isinstance(a.get("params"), dict) else {}
                    # Require either explicit placement or x/y to avoid off-screen defaults.
                    if "caption_placement" not in params and not (
                        params.get("x") is not None and params.get("y") is not None
                    ):
                        errors.append("refiner_caption_missing_placement")
                        break
                    px = _to_float(params.get("x"), -1.0)
                    py = _to_float(params.get("y"), -1.0)
                    if width > 0 and px >= 0.0 and not (70.0 <= px <= width - 70.0):
                        errors.append("refiner_caption_outside_safe_x")
                    if height > 0 and py >= 0.0 and not (120.0 <= py <= height - 80.0):
                        errors.append("refiner_caption_outside_safe_y")
                    fs = _to_float(params.get("font_size"), 56.0)
                    if not (20.0 <= fs <= 110.0):
                        errors.append("refiner_caption_unreasonable_font_size")
                    if idx + 1 < len(actions):
                        nxt = actions[idx + 1]
                        if isinstance(nxt, dict):
                            nxt_s = _to_float(nxt.get("t_start"), te)
                            if abs(nxt_s - te) > 0.08:
                                errors.append("refiner_caption_non_contiguous_timing")

    if planner_text:
        needed = planner_element_ids(planner_text)
        missing = sorted(needed - element_ids)
        if missing:
            errors.append("refiner_missing_planner_elements")
            details["missing_planner_elements"] = missing

    if max_action_end <= 0.0:
        errors.append("refiner_empty_timeline")

    unique_errors = sorted(set(errors))
    details["element_count"] = len(elements)
    details["element_ids"] = sorted(element_ids)
    details["max_action_end"] = round(max_action_end, 3)

    score = 1.0
    # Penalize missing structural items more heavily.
    heavy = [e for e in unique_errors if any(x in e for x in ("missing_video", "missing_elements", "missing_planner_elements"))]
    score -= 0.2 * len(heavy)
    score -= 0.05 * (len(unique_errors) - len(heavy))
    score = max(0.0, round(score, 4))
    return ContractCheck(ok=not unique_errors, score=score, errors=unique_errors, details=details)


def check_refiner_text(text: str, planner_text: str = "") -> ContractCheck:
    inter = parse_jsonish(text)
    if inter is None:
        return ContractCheck(False, 0.0, ["refiner_not_json"], {})
    return check_refiner_inter(inter, planner_text=planner_text)


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
