from __future__ import annotations

import json
from typing import Any


REQUIRED_SEGMENT_KEYS = (
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

ALLOWED_VISUAL_ROLES = {"supporting_visual", "accent", "unused"}
AUDIO_TYPES = {"audio", "music", "sfx"}
CAPTION_TYPES = {"caption"}
VISUAL_TYPES = {"video", "image", "gif", "sticker"}


def parse_planner_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Planner output is empty.")
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        obj = _safe_json_loads(raw)
    except json.JSONDecodeError:
        obj = _extract_first_json_object(raw)
    if not isinstance(obj, dict):
        raise ValueError("Planner output is not a JSON object.")
    return obj


def validate_planner_output(
    planner: dict[str, Any],
    grouped_caption_map: list[dict[str, Any]],
    asset_registry: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(planner, dict):
        return ["planner must be a JSON object"]
    for k in ("video_summary", "asset_understanding", "segments"):
        if k not in planner:
            errors.append(f"missing top-level key '{k}'")

    video_summary = planner.get("video_summary")
    if not isinstance(video_summary, dict):
        errors.append("video_summary must be an object")
    else:
        main_audio = str(video_summary.get("main_audio", "")).strip()
        main_caption = str(video_summary.get("main_caption", "")).strip()
        if not _is_audio_id(main_audio, asset_registry):
            errors.append("video_summary.main_audio must be an existing audio element id")
        if not _is_caption_id(main_caption, asset_registry):
            errors.append("video_summary.main_caption must be an existing caption element id")

    au = planner.get("asset_understanding")
    if not isinstance(au, list):
        errors.append("asset_understanding must be a list")
    else:
        listed_ids = {str(x.get("element_id")).strip() for x in au if isinstance(x, dict) and x.get("element_id")}
        for aid in sorted(asset_registry.keys()):
            if aid not in listed_ids:
                errors.append(f"asset_understanding missing asset '{aid}'")
        for item in au:
            if not isinstance(item, dict):
                continue
            eid = str(item.get("element_id", "")).strip()
            role = str(item.get("suggested_role", "")).strip().lower()
            et = _asset_type(eid, asset_registry)

            if et in AUDIO_TYPES and role != "main_audio":
                errors.append(f"asset_understanding for audio '{eid}' must have suggested_role='main_audio'")
            if et in {"video", "image"} and role not in {"supporting_visual", "unused"}:
                errors.append(f"asset_understanding for visual '{eid}' must be supporting_visual or unused")
            if et in {"gif", "sticker"} and role not in {"accent", "unused"}:
                errors.append(f"asset_understanding for accent '{eid}' must be accent or unused")

    segments = planner.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append("segments must be a non-empty list")
        return errors

    expected_idx = [int(x.get("index")) for x in grouped_caption_map if isinstance(x, dict) and isinstance(x.get("index"), int)]
    seen: list[int] = []
    first_owner: dict[int, int] = {}

    for si, seg in enumerate(segments):
        ctx = f"segments[{si}]"
        if not isinstance(seg, dict):
            errors.append(f"{ctx} must be an object")
            continue
        for key in REQUIRED_SEGMENT_KEYS:
            if key not in seg:
                errors.append(f"{ctx} missing '{key}'")
        cap_idx = seg.get("caption_indices")
        if not isinstance(cap_idx, list) or not cap_idx or not all(isinstance(i, int) for i in cap_idx):
            errors.append(f"{ctx}.caption_indices must be a non-empty list of integers")
            continue
        for i in cap_idx:
            seen.append(i)
            first_owner.setdefault(i, si)
        grp = _caption_rows_for_indices(grouped_caption_map, cap_idx)
        if len(grp) != len(cap_idx):
            errors.append(f"{ctx} contains caption index not found in grouped_caption_map")
            continue
        t_start = _f(seg.get("t_start"))
        t_end = _f(seg.get("t_end"))
        if t_start is None or t_end is None:
            errors.append(f"{ctx} t_start/t_end must be numeric")
        else:
            if abs(t_start - _f(grp[0].get("start"), 0.0)) > 1e-6:
                errors.append(f"{ctx}.t_start must match first caption start")
            if abs(t_end - _f(grp[-1].get("end"), 0.0)) > 1e-6:
                errors.append(f"{ctx}.t_end must match last caption end")
        expected_spoken = _join_caption_text(grp)
        if str(seg.get("spoken_text", "")).strip() != expected_spoken:
            errors.append(f"{ctx}.spoken_text must exactly match caption_indices text")

        vc = seg.get("visual_candidates")
        if not isinstance(vc, list):
            errors.append(f"{ctx}.visual_candidates must be a list")
            continue
        seg_boundaries = _segment_boundaries_set(grp)
        for vi, cand in enumerate(vc):
            vctx = f"{ctx}.visual_candidates[{vi}]"
            if not isinstance(cand, dict):
                errors.append(f"{vctx} must be an object")
                continue
            eid = str(cand.get("element_id", "")).strip()
            et = _asset_type(eid, asset_registry)
            if et in AUDIO_TYPES:
                errors.append(f"{vctx} cannot include audio element '{eid}'")
            if et in CAPTION_TYPES:
                errors.append(f"{vctx} cannot include caption element '{eid}'")
            role = str(cand.get("role", "")).strip().lower()
            if role not in ALLOWED_VISUAL_ROLES:
                errors.append(f"{vctx} role '{role}' is invalid")
            th = cand.get("time_hint")
            if isinstance(th, dict):
                hs = _f(th.get("start"))
                he = _f(th.get("end"))
                if hs is None or he is None:
                    errors.append(f"{vctx}.time_hint.start/end must be numeric")
                else:
                    if hs not in seg_boundaries or he not in seg_boundaries:
                        errors.append(f"{vctx}.time_hint must use grouped_caption_map boundaries")
                    if t_start is not None and hs < t_start - 1e-6:
                        errors.append(f"{vctx}.time_hint.start outside segment")
                    if t_end is not None and he > t_end + 1e-6:
                        errors.append(f"{vctx}.time_hint.end outside segment")
                    if he <= hs:
                        errors.append(f"{vctx}.time_hint has invalid range")

    expected_set = set(expected_idx)
    seen_set = set(seen)
    missing = sorted(expected_set - seen_set)
    if missing:
        errors.append(f"missing caption indices: {missing}")
    dupes = sorted(i for i in seen_set if seen.count(i) > 1)
    if dupes:
        errors.append(f"duplicate caption indices: {dupes}")
    if _appears_repeated_payload(planner):
        errors.append("planner output appears repeated/truncated")
    return errors


def fix_planner_output(
    planner: dict[str, Any],
    grouped_caption_map: list[dict[str, Any]],
    asset_registry: dict[str, Any],
) -> dict[str, Any]:
    out = dict(planner if isinstance(planner, dict) else {})
    out.setdefault("video_summary", {})
    out.setdefault("asset_understanding", [])
    out.setdefault("segments", [])
    out.setdefault("creative_suggestions", [])
    out.setdefault("needs_user_input", [])

    video_summary = out["video_summary"] if isinstance(out["video_summary"], dict) else {}
    out["video_summary"] = video_summary
    if not _is_audio_id(str(video_summary.get("main_audio", "")).strip(), asset_registry):
        audio_ids = [k for k in asset_registry if _asset_type(k, asset_registry) in AUDIO_TYPES]
        if audio_ids:
            video_summary["main_audio"] = audio_ids[0]
    if not _is_caption_id(str(video_summary.get("main_caption", "")).strip(), asset_registry):
        video_summary["main_caption"] = "caption_track_1" if "caption_track_1" in asset_registry else _first_caption_id(asset_registry)

    au = [x for x in out["asset_understanding"] if isinstance(x, dict)] if isinstance(out["asset_understanding"], list) else []
    by_id = {str(x.get("element_id")).strip(): x for x in au if x.get("element_id")}
    for aid in sorted(asset_registry.keys()):
        if aid not in by_id:
            by_id[aid] = {
                "element_id": aid,
                "type": _asset_type(aid, asset_registry),
                "represents": "",
                "suggested_role": "supporting_visual",
                "best_use": "",
                "usefulness": "medium",
            }
    out["asset_understanding"] = list(by_id.values())

    groups_by_idx = {int(x["index"]): x for x in grouped_caption_map if isinstance(x, dict) and isinstance(x.get("index"), int)}
    segments_in = [x for x in out["segments"] if isinstance(x, dict)] if isinstance(out["segments"], list) else []

    used_once: set[int] = set()
    fixed_segments: list[dict[str, Any]] = []
    for seg in segments_in:
        cap_idx = [i for i in seg.get("caption_indices", []) if isinstance(i, int) and i in groups_by_idx]
        unique_idx: list[int] = []
        for i in cap_idx:
            if i in used_once:
                continue
            used_once.add(i)
            unique_idx.append(i)
        if not unique_idx:
            continue
        unique_idx.sort()
        grp = [groups_by_idx[i] for i in unique_idx]
        nseg = dict(seg)
        nseg["caption_indices"] = unique_idx
        nseg["t_start"] = _f(grp[0].get("start"), 0.0)
        nseg["t_end"] = _f(grp[-1].get("end"), 0.0)
        nseg["spoken_text"] = _join_caption_text(grp)
        nseg["segment_purpose"] = str(nseg.get("segment_purpose", "")).strip() or "Caption-driven segment."
        nseg["caption_instruction"] = str(nseg.get("caption_instruction", "")).strip() or "Render captions clearly."
        nseg["transition_intent"] = str(nseg.get("transition_intent", "")).strip() or "cut"
        nseg["visual_candidates"] = _fix_visual_candidates(
            nseg.get("visual_candidates"),
            grp,
            nseg["t_start"],
            nseg["t_end"],
            asset_registry,
        )
        fixed_segments.append(nseg)

    # fallback segments for missing caption indices
    all_idx = sorted(groups_by_idx.keys())
    missing = [i for i in all_idx if i not in used_once]
    for i in missing:
        g = groups_by_idx[i]
        fixed_segments.append(
            {
                "segment_id": "",
                "t_start": _f(g.get("start"), 0.0),
                "t_end": _f(g.get("end"), 0.0),
                "caption_indices": [i],
                "spoken_text": str(g.get("text", "")).strip(),
                "segment_purpose": "Fallback caption-only segment for uncovered caption index.",
                "visual_candidates": [],
                "caption_instruction": "Caption-focused segment.",
                "transition_intent": "cut",
            }
        )

    fixed_segments.sort(key=lambda s: (_f(s.get("t_start"), 0.0), _f(s.get("t_end"), 0.0)))
    for i, seg in enumerate(fixed_segments, start=1):
        seg["segment_id"] = f"seg_{i:03d}"
    out["segments"] = fixed_segments
    return out


def validate_and_fix_planner_output(
    planner: dict[str, Any],
    grouped_caption_map: list[dict[str, Any]],
    asset_registry: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors_before = validate_planner_output(planner, grouped_caption_map, asset_registry)
    fixed = fix_planner_output(planner, grouped_caption_map, asset_registry)
    errors_after = validate_planner_output(fixed, grouped_caption_map, asset_registry)
    return fixed, [*errors_before, *[f"POST_FIX: {e}" for e in errors_after]]


def _extract_first_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in planner output.")
    in_str = False
    esc = False
    depth = 0
    begin = -1
    for i in range(start, len(text)):
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
            continue
        if ch == "{":
            if depth == 0:
                begin = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and begin >= 0:
                candidate = text[begin : i + 1]
                try:
                    obj = _safe_json_loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
    raise ValueError("Could not extract valid JSON object from planner output.")


def _caption_rows_for_indices(grouped_caption_map: list[dict[str, Any]], indices: list[int]) -> list[dict[str, Any]]:
    lookup = {int(x["index"]): x for x in grouped_caption_map if isinstance(x, dict) and isinstance(x.get("index"), int)}
    return [lookup[i] for i in indices if i in lookup]


def _join_caption_text(rows: list[dict[str, Any]]) -> str:
    return " ".join(str(r.get("text", "")).strip() for r in rows).strip()


def _segment_boundaries_set(rows: list[dict[str, Any]]) -> set[float]:
    out: set[float] = set()
    for r in rows:
        out.add(_f(r.get("start"), 0.0))
        out.add(_f(r.get("end"), 0.0))
    return out


def _fix_visual_candidates(
    visual_candidates: Any,
    group_rows: list[dict[str, Any]],
    seg_start: float,
    seg_end: float,
    asset_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    vc = [x for x in (visual_candidates if isinstance(visual_candidates, list) else []) if isinstance(x, dict)]
    boundaries = sorted(_segment_boundaries_set(group_rows))
    out: list[dict[str, Any]] = []
    for cand in vc:
        eid = str(cand.get("element_id", "")).strip()
        if not eid:
            continue
        et = _asset_type(eid, asset_registry)
        if et in AUDIO_TYPES or et in CAPTION_TYPES:
            continue
        nc = dict(cand)
        role = str(nc.get("role", "")).strip().lower()
        if role not in ALLOWED_VISUAL_ROLES:
            if et in {"gif", "sticker"}:
                role = "accent"
            elif et in {"video", "image"}:
                role = "supporting_visual"
            else:
                role = "supporting_visual"
        # normalize per rule
        if et in {"video", "image"}:
            role = "supporting_visual"
        if et in {"gif", "sticker"}:
            role = "accent"
        nc["role"] = role

        th = nc.get("time_hint")
        fixed_th = _fix_time_hint(th, boundaries, seg_start, seg_end)
        if fixed_th is None:
            continue
        nc["time_hint"] = fixed_th
        out.append(nc)
    return out


def _fix_time_hint(
    time_hint: Any,
    boundaries: list[float],
    seg_start: float,
    seg_end: float,
) -> dict[str, float] | None:
    if not boundaries:
        return None
    if not isinstance(time_hint, dict):
        return {"start": seg_start, "end": seg_end}
    hs = _f(time_hint.get("start"))
    he = _f(time_hint.get("end"))
    if hs is None or he is None:
        return {"start": seg_start, "end": seg_end}
    hs2 = _nearest_inside(hs, boundaries, seg_start, seg_end)
    he2 = _nearest_inside(he, boundaries, seg_start, seg_end)
    if hs2 is None or he2 is None:
        return None
    if he2 <= hs2:
        i = boundaries.index(hs2) if hs2 in boundaries else -1
        if i >= 0 and i + 1 < len(boundaries):
            he2 = boundaries[i + 1]
        else:
            return None
    if hs2 < seg_start - 1e-6 or he2 > seg_end + 1e-6:
        return None
    return {"start": hs2, "end": he2}


def _nearest_inside(v: float, boundaries: list[float], s: float, e: float) -> float | None:
    inside = [x for x in boundaries if s - 1e-6 <= x <= e + 1e-6]
    if not inside:
        return None
    return min(inside, key=lambda x: abs(x - v))


def _asset_type(element_id: str, asset_registry: dict[str, Any]) -> str:
    row = asset_registry.get(element_id, {})
    t = str((row or {}).get("type", "")).strip().lower()
    return t


def _is_audio_id(element_id: str, asset_registry: dict[str, Any]) -> bool:
    return bool(element_id) and _asset_type(element_id, asset_registry) in AUDIO_TYPES


def _is_caption_id(element_id: str, asset_registry: dict[str, Any]) -> bool:
    return bool(element_id) and _asset_type(element_id, asset_registry) in CAPTION_TYPES


def _first_caption_id(asset_registry: dict[str, Any]) -> str:
    for k in asset_registry:
        if _asset_type(k, asset_registry) in CAPTION_TYPES:
            return k
    return "caption_track_1"


def _appears_repeated_payload(planner: dict[str, Any]) -> bool:
    segs = planner.get("segments")
    if not isinstance(segs, list) or len(segs) < 2:
        return False
    ids = [str(s.get("segment_id", "")) for s in segs if isinstance(s, dict)]
    return len(ids) != len(set(ids))


def _f(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except Exception:
        return default


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = _strip_invalid_control_chars(text)
        return json.loads(cleaned)


def _strip_invalid_control_chars(text: str) -> str:
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if o < 32 and ch not in ("\n", "\r", "\t"):
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)
