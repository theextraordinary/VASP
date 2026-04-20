from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vasp.a2v.v2.creativity_policy import (
    BOTTOM_CAPTION_LAYOUT,
    CENTER_CAPTION_LAYOUT,
    DEFAULT_CAPTION_STYLE,
    FIXED_VISUAL_LAYOUT,
    allowed_animation,
    allowed_transition,
    clamp_visual_layout,
    creative_background,
    creative_caption_animation,
    creative_caption_style,
    get_creativity_policy,
    normalize_caption_layout,
    normalize_caption_style,
)
from vasp.a2v.v2.preset_backgrounds_v3 import choose_preset_background, get_preset_background
from vasp.a2v.v2.refiner_presets_v3 import (
    get_animation_preset,
    get_background_preset,
    get_caption_preset,
    get_layout_preset,
    get_transition_preset,
    resolve_refiner_preset_bundle,
)
from vasp.a2v.v3.schemas import InterAudio, InterCanvas, InterV3
from vasp.a2v.v3.utils import is_visual_media, main_audio, main_video, media_inputs, media_probe, media_by_id, parse_jsonish_file, write_json

VISUAL_800_CROP_LAYOUT = {
    **FIXED_VISUAL_LAYOUT,
    "height": 800,
    "fit": "cover",
}


def _iter_refined_files(path: Path) -> list[Path]:
    # The pipeline stores both normalized segment_XXX.json files and raw LLM
    # dumps as segment_XXX.raw.txt. Prefer the normalized JSON files so the same
    # segment is not combined twice.
    json_files = sorted(p for p in path.glob("*.json") if p.is_file())
    if json_files:
        return json_files
    files = sorted(path.glob("*.md")) + sorted(path.glob("*.txt"))
    return [p for p in files if p.is_file() and not p.name.endswith(".raw.txt")]


def _time_key(value: Any) -> float:
    try:
        return round(float(value), 3)
    except Exception:
        return 0.0


def _dedupe_backgrounds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            _time_key(row.get("t_start")),
            _time_key(row.get("t_end")),
            row.get("type"),
            row.get("color"),
            row.get("secondary_color"),
            _time_key(row.get("opacity", 1.0)),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _dedupe_captions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("caption_group_index") is not None:
            key = ("caption_group_index", row.get("caption_group_index"))
        else:
            key = (
                "caption_text_time",
                str(row.get("text") or "").strip(),
                _time_key(row.get("t_start")),
                _time_key(row.get("t_end")),
            )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _dedupe_visuals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        layout = row.get("layout") if isinstance(row.get("layout"), dict) else {}
        key = (
            row.get("source_ref") or row.get("element_id"),
            _time_key(row.get("t_start")),
            _time_key(row.get("t_end")),
            _time_key(layout.get("x")),
            _time_key(layout.get("y")),
            _time_key(layout.get("width")),
            _time_key(layout.get("height")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _resolve_visual_overlaps(rows: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    ordered = sorted(
        [dict(row) for row in rows if isinstance(row, dict)],
        key=lambda x: (float(x.get("t_start", 0.0) or 0.0), float(x.get("t_end", 0.0) or 0.0)),
    )
    out: list[dict[str, Any]] = []
    for row in ordered:
        try:
            start = float(row.get("t_start", 0.0) or 0.0)
            end = float(row.get("t_end", 0.0) or 0.0)
        except Exception:
            warnings.append(f"visual_invalid_timing:{row.get('element_id') or row.get('source_ref') or '(unknown)'}")
            continue
        if end <= start:
            warnings.append(f"visual_drop_zero_duration:{row.get('element_id') or row.get('source_ref') or '(unknown)'}")
            continue
        if out:
            prev = out[-1]
            prev_end = float(prev.get("t_end", 0.0) or 0.0)
            if prev_end > start:
                prev_id = prev.get("element_id") or prev.get("source_ref") or "(unknown)"
                prev["t_end"] = round(start, 3)
                warnings.append(f"visual_overlap_trimmed:{prev_id}:{round(prev_end, 3)}->{round(start, 3)}")
                if float(prev.get("t_end", 0.0) or 0.0) <= float(prev.get("t_start", 0.0) or 0.0):
                    dropped = out.pop()
                    warnings.append(f"visual_overlap_drop_zero:{dropped.get('element_id') or dropped.get('source_ref') or '(unknown)'}")
        out.append(row)
    return out


def _visual_id_from_row(row: dict[str, Any]) -> str:
    return str(row.get("source_ref") or row.get("element_id") or "").strip()


def _visual_media_ids(media_json: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for row in media_inputs(media_json):
        if not isinstance(row, dict) or not is_visual_media(row):
            continue
        eid = str(row.get("id") or "").strip()
        if eid:
            ids.append(eid)
    return ids


def _caption_gap_intervals(captions: list[dict[str, Any]], visuals: list[dict[str, Any]]) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for caption in sorted(captions, key=lambda c: (float(c.get("t_start", 0.0) or 0.0), float(c.get("t_end", 0.0) or 0.0))):
        start = _safe_float(caption.get("t_start"))
        end = _safe_float(caption.get("t_end"))
        if start is None or end is None or end <= start:
            continue
        has_visual = any(
            _overlaps(start, end, float(v.get("t_start", 0.0) or 0.0), float(v.get("t_end", 0.0) or 0.0))
            for v in visuals
            if isinstance(v, dict)
        )
        if not has_visual:
            intervals.append((start, end))

    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + 0.03:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [(round(s, 3), round(e, 3)) for s, e in merged if e > s]


def _caption_overlaps_any_visual(caption: dict[str, Any], visuals: list[dict[str, Any]]) -> bool:
    start = _safe_float(caption.get("t_start"))
    end = _safe_float(caption.get("t_end"))
    if start is None or end is None or end <= start:
        return False
    return any(
        _overlaps(start, end, float(v.get("t_start", 0.0) or 0.0), float(v.get("t_end", 0.0) or 0.0))
        for v in visuals
        if isinstance(v, dict)
    )


def _keep_only_caption_only_cues(
    captions: list[dict[str, Any]],
    visuals: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    hidden = 0
    for caption in captions:
        if _caption_overlaps_any_visual(caption, visuals):
            hidden += 1
            continue
        kept.append(caption)
    warnings.append(f"captions_hidden_where_visual_active:{hidden}")
    warnings.append(f"captions_kept_for_no_visual_segments:{len(kept)}")
    return kept


def _fill_no_caption_visual_gaps(
    *,
    disabled_captions: list[dict[str, Any]],
    visuals_raw: list[dict[str, Any]],
    media_json: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    if not disabled_captions:
        return visuals_raw
    visual_ids = _visual_media_ids(media_json)
    if not visual_ids:
        warnings.append("no_caption_gap_fill_no_visual_media_available")
        return visuals_raw

    used_ids = {_visual_id_from_row(row) for row in visuals_raw if isinstance(row, dict) and _visual_id_from_row(row)}
    unused_ids = [eid for eid in visual_ids if eid not in used_ids]
    if not unused_ids:
        warnings.append("no_caption_unmatched_text_no_unused_media_left")
        return visuals_raw
    unmatched_captions = [
        c for c in disabled_captions
        if isinstance(c, dict) and bool(c.get("_unmatched_caption_only"))
    ]
    if not unmatched_captions:
        warnings.append("no_caption_unmatched_text_none_found")
        return visuals_raw
    intervals = _caption_gap_intervals(unmatched_captions, visuals_raw)
    if not intervals:
        return visuals_raw

    filled = list(visuals_raw)
    for idx, (start, end) in enumerate(intervals):
        if idx >= len(unused_ids):
            warnings.append("no_caption_unmatched_text_more_intervals_than_unused_media")
            break
        eid = unused_ids[idx]
        filled.append(
            {
                "element_id": eid,
                "source_ref": eid,
                "type": "image",
                "t_start": start,
                "t_end": end,
                "layout": dict(VISUAL_800_CROP_LAYOUT),
                "transition_in": {"type": "fade", "duration": 0.08},
                "transition_out": {"type": "fade", "duration": 0.08},
                "animation": {"type": "none", "intensity": "low"},
                "reason": "no_caption_unmatched_text_paired_with_unused_media",
            }
        )
        warnings.append(f"no_caption_unmatched_text_paired:{eid}:{start:.3f}-{end:.3f}")
    return filled


def _clamp_rows_to_duration(rows: list[dict[str, Any]], duration: float, kind: str, warnings: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        n = dict(row)
        start = _safe_float(n.get("t_start"))
        end = _safe_float(n.get("t_end"))
        if start is None:
            warnings.append(f"{kind}_drop_missing_start:{idx}")
            continue
        if end is None:
            warnings.append(f"{kind}_drop_missing_end:{idx}")
            continue
        if start >= duration:
            warnings.append(f"{kind}_drop_after_duration:{idx}:{start:.3f}>={duration:.3f}")
            continue
        if end > duration:
            n["t_end"] = duration
            warnings.append(f"{kind}_clamped_to_duration:{idx}:{end:.3f}->{duration:.3f}")
        if float(n.get("t_end", 0.0) or 0.0) <= start:
            warnings.append(f"{kind}_drop_zero_after_clamp:{idx}")
            continue
        out.append(n)
    return out


def _main_visual_duration(media_json: dict[str, Any]) -> float:
    probe = media_probe(media_json)
    best = 0.0
    for row in media_inputs(media_json):
        if not isinstance(row, dict) or not is_visual_media(row):
            continue
        eid = str(row.get("id") or "")
        info = probe.get(eid)
        if not isinstance(info, dict):
            continue
        try:
            dur = float(info.get("duration") or 0.0)
        except Exception:
            dur = 0.0
        best = max(best, dur)
    return round(best, 3)


def _is_main_video_row(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(k) or "")
        for k in ("role", "aim", "about", "tags")
    ).lower()
    return any(
        marker in text
        for marker in (
            "main video",
            "main visual",
            "extract speech",
            "extract captions",
            "speech captions",
            "caption source",
        )
    )


def _should_use_base_video(media_json: dict[str, Any], base_video_id: str | None, audio_id: str | None) -> bool:
    if not base_video_id:
        return False
    row = media_by_id(media_json).get(base_video_id)
    if not isinstance(row, dict):
        return False
    if not audio_id:
        return True
    return _is_main_video_row(row)


def _overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def _clamp_box(layout: dict[str, Any], *, visual: bool = False) -> dict[str, Any]:
    n = dict(layout)
    x = max(0.0, min(1080.0, float(n.get("x", 0.0) or 0.0)))
    y = max(0.0, min(1920.0, float(n.get("y", 0.0) or 0.0)))
    w = max(1.0, min(1080.0 - x, float(n.get("width", 840.0) or 840.0)))
    h = max(1.0, min(1920.0 - y, float(n.get("height", 300.0) or 300.0)))
    n.update({"x": x, "y": y, "width": w, "height": h})
    if visual:
        n["opacity"] = max(1.0, float(n.get("opacity", 1.0) or 1.0))
        n.setdefault("fit", "contain")
    return n


def _merge_preset(base: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update({k: v for k, v in raw.items() if v is not None})
    return merged


def _without_helper_keys(row: dict[str, Any]) -> dict[str, Any]:
    helper = {
        "preset",
        "override",
        "style_override",
        "layout_override",
        "animation_override",
        "background_preset",
        "background_image_preset",
        "caption_preset",
        "caption_layout_preset",
        "caption_animation_preset",
        "visual_layout_preset",
        "visual_animation_preset",
        "transition_preset",
        "preset_note",
    }
    return {k: v for k, v in row.items() if k not in helper and v is not None}


def _segment_preset_bundle(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "preset_bundle": obj.get("preset_bundle"),
        "background_preset": obj.get("background_preset"),
        "background_image_preset": obj.get("background_image_preset"),
        "caption_preset": obj.get("caption_preset"),
        "caption_layout_preset": obj.get("caption_layout_preset"),
        "visual_layout_preset": obj.get("visual_layout_preset"),
        "caption_animation_preset": obj.get("caption_animation_preset"),
        "visual_animation_preset": obj.get("visual_animation_preset"),
        "transition_preset": obj.get("transition_preset"),
    }


def _segment_seed(obj: dict[str, Any]) -> int:
    sid = str(obj.get("segment_id") or "")
    digits = "".join(ch for ch in sid if ch.isdigit())
    if digits:
        return int(digits)
    try:
        return int(float(obj.get("t_start", 0.0) or 0.0) * 10)
    except Exception:
        return 0


def _has_any_preset_name(names: dict[str, Any]) -> bool:
    return any(str(v or "").strip() for v in names.values())


def _fallback_preset_names(obj: dict[str, Any], creativity_level: int, has_visual: bool) -> dict[str, str]:
    if creativity_level <= 0:
        return {
            "preset_bundle": "clean_educational",
            "background_preset": "black_reel_canvas",
            "caption_preset": "bottom_subtitle_clean",
            "caption_layout_preset": "caption_bottom_safe" if has_visual else "caption_only_center",
            "visual_layout_preset": "visual_center_800h",
            "caption_animation_preset": "caption_word_reveal_fast",
            "visual_animation_preset": "visual_none",
            "transition_preset": "quick_cut",
        }
    caption_only = ["emotional_quote", "dark_mystery", "cinematic_history", "clean_educational"]
    visual = ["science_discovery", "cinematic_history", "clean_educational", "space_neon", "meme_pop", "breaking_news", "war_documentary", "comedy_reaction"]
    bundle_name = (visual if has_visual else caption_only)[_segment_seed(obj) % len(visual if has_visual else caption_only)]
    resolved = resolve_refiner_preset_bundle(bundle_name)["names"]
    out = {k: str(v) for k, v in resolved.items() if isinstance(v, str)}
    out["caption_layout_preset"] = "caption_bottom_safe" if has_visual else "caption_only_center"
    if creativity_level <= 2:
        out["visual_layout_preset"] = "visual_center_800h"
    return out


def _bundle_with_safe_fallback(obj: dict[str, Any], names: dict[str, Any], creativity_level: int, has_visual: bool, warnings: list[str]) -> dict[str, Any]:
    fallback_names = _fallback_preset_names(obj, creativity_level, has_visual)
    clean_names = {k: v for k, v in names.items() if isinstance(v, str) and v.strip()}
    bundle = resolve_refiner_preset_bundle(clean_names)
    checks = (
        ("background", "background_preset"),
        ("caption_style", "caption_preset"),
        ("caption_layout", "caption_layout_preset"),
        ("visual_layout", "visual_layout_preset"),
        ("caption_animation", "caption_animation_preset"),
        ("visual_animation", "visual_animation_preset"),
        ("transition", "transition_preset"),
    )
    fixed_names = dict(clean_names)
    changed = False
    for component, name_key in checks:
        if not bundle.get(component):
            original = clean_names.get(name_key)
            fallback = fallback_names.get(name_key)
            if original:
                warnings.append(f"unknown_refiner_preset:{name_key}:{original}")
            if fallback:
                fixed_names[name_key] = fallback
                changed = True
    if not fixed_names.get("preset_bundle"):
        fixed_names["preset_bundle"] = fallback_names.get("preset_bundle", "clean_educational")
        changed = True
    if changed:
        bundle = resolve_refiner_preset_bundle(fixed_names)
    return bundle


def _row_background_base(row: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    preset_name = str(row.get("background_preset") or row.get("preset") or "").strip()
    return get_background_preset(preset_name) or dict(fallback)


def _apply_preset_background_image(
    bg: dict[str, Any],
    obj: dict[str, Any],
    *,
    use_preset_backgrounds: bool,
    has_visual: bool,
    creativity_level: int,
    warnings: list[str],
) -> dict[str, Any]:
    if not use_preset_backgrounds:
        return bg
    if str(bg.get("source_path") or bg.get("path") or "").strip():
        return bg
    bg_name = str(
        bg.get("background_image_preset")
        or bg.get("preset_background")
        or obj.get("background_image_preset")
        or ""
    ).strip()
    preset = get_preset_background(bg_name)
    if not preset:
        caption_centered = not has_visual
        preset = choose_preset_background(
            has_visual=has_visual,
            caption_centered=caption_centered,
            segment_text=str(obj.get("matched_text") or ""),
            creativity_level=creativity_level,
            seed=_segment_seed(obj),
        )
        bg_name = str(preset.get("name") or "")
        warnings.append(f"preset_background_fallback:{obj.get('segment_id')}:{bg_name}")
    if not preset:
        return bg
    out = dict(bg)
    out.update(
        {
            "type": "image",
            "background_image_preset": preset["name"],
            "source_path": preset["path"],
            "fit": "cover",
            "opacity": float(out.get("opacity", 1.0) or 1.0),
            "reason": f"preset_background:{preset['name']}:{preset['best_use']}",
        }
    )
    return out


def _row_caption_style_base(row: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    return get_caption_preset(str(row.get("caption_preset") or "").strip()) or dict(fallback)


def _row_layout_base(row: dict[str, Any], key: str, fallback: dict[str, Any]) -> dict[str, Any]:
    return get_layout_preset(str(row.get(key) or "").strip()) or dict(fallback)


def _row_animation_base(row: dict[str, Any], key: str, fallback: dict[str, Any]) -> dict[str, Any]:
    return get_animation_preset(str(row.get(key) or "").strip()) or dict(fallback)


def _row_transition_base(row: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    return get_transition_preset(str(row.get("transition_preset") or "").strip()) or dict(fallback)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _caption_groups_from_source_segment(source_segment: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(source_segment, dict):
        return []
    groups = source_segment.get("caption_groups")
    if not isinstance(groups, list):
        return []
    return [g for g in groups if isinstance(g, dict)]


def _repair_caption_timing_from_source(
    obj: dict[str, Any],
    source_segment: dict[str, Any] | None,
    warnings: list[str],
) -> dict[str, Any]:
    groups = _caption_groups_from_source_segment(source_segment)
    if not groups:
        return obj

    by_index: dict[int, dict[str, Any]] = {}
    by_text: dict[str, dict[str, Any]] = {}
    for idx, group in enumerate(groups):
        raw_index = group.get("index")
        try:
            group_index = int(raw_index)
        except Exception:
            group_index = idx
        by_index[group_index] = group
        by_text[str(group.get("text") or "").strip().lower()] = group

    rows = obj.get("caption_timeline") if isinstance(obj.get("caption_timeline"), list) else []
    repaired: list[dict[str, Any]] = []
    used_indices: set[int] = set()
    for row_pos, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        n = dict(row)
        group: dict[str, Any] | None = None
        raw_cgi = n.get("caption_group_index")
        try:
            cgi = int(raw_cgi)
        except Exception:
            cgi = None
        if cgi is not None:
            group = by_index.get(cgi)
        if group is None:
            group = by_text.get(str(n.get("text") or "").strip().lower())
        if group is None and row_pos < len(groups):
            group = groups[row_pos]

        if group is not None:
            group_index = int(group.get("index", row_pos) or row_pos)
            used_indices.add(group_index)
            group_start = _safe_float(group.get("start"))
            group_end = _safe_float(group.get("end"))
            group_text = str(group.get("text") or "").strip()
            old_start = _safe_float(n.get("t_start"))
            old_end = _safe_float(n.get("t_end"))
            old_text = str(n.get("text") or "").strip()
            if group_start is not None:
                n["t_start"] = group_start
                if old_start is None or abs(old_start - group_start) > 0.01:
                    warnings.append(f"caption_t_start_repaired:{obj.get('segment_id')}:{group_index}")
            if group_end is not None:
                n["t_end"] = group_end
                if old_end is None or abs(old_end - group_end) > 0.01:
                    warnings.append(f"caption_t_end_repaired:{obj.get('segment_id')}:{group_index}")
            n["caption_group_index"] = group_index
            if group_text:
                n["text"] = group_text
                if old_text and old_text != group_text:
                    warnings.append(f"caption_text_repaired:{obj.get('segment_id')}:{group_index}")
        repaired.append(n)

    # If the refiner omitted a cue entirely, preserve caption visibility by
    # adding a minimal cue from the source segment. Styling/presets are applied
    # later in the same combiner path.
    for fallback_pos, group in enumerate(groups):
        group_index = int(group.get("index", fallback_pos) or fallback_pos)
        if group_index in used_indices:
            continue
        start = _safe_float(group.get("start"))
        end = _safe_float(group.get("end"))
        text = str(group.get("text") or "").strip()
        if start is None or end is None or end <= start or not text:
            continue
        repaired.append(
            {
                "caption_group_index": group_index,
                "text": text,
                "t_start": start,
                "t_end": end,
                "highlight_words": [],
            }
        )
        warnings.append(f"caption_cue_added_from_source:{obj.get('segment_id')}:{group_index}")

    obj = dict(obj)
    obj["caption_timeline"] = repaired
    return obj


def _source_segment_path_for_refined(refined_file: Path) -> Path | None:
    candidate = refined_file.parent.parent / "generated_segments" / f"{refined_file.stem}.md"
    return candidate if candidate.exists() else None


def _resolve_visual_sources(
    visuals: list[dict[str, Any]],
    media_json: dict[str, Any],
    warnings: list[str],
    creativity_level: int,
) -> list[dict[str, Any]]:
    by_id = media_by_id(media_json)
    out: list[dict[str, Any]] = []
    for v in visuals:
        if not isinstance(v, dict):
            continue
        eid = str(v.get("source_ref") or v.get("element_id") or "").strip()
        if not eid or eid not in by_id:
            warnings.append(f"visual_media_missing:{eid}")
            continue
        row = by_id[eid]
        if not is_visual_media(row):
            warnings.append(f"visual_media_not_visual:{eid}")
            continue
        n = dict(v)
        n["element_id"] = eid
        n["source_ref"] = eid
        n["source_path"] = str(row.get("path") or "")
        n["type"] = str(row.get("media_type") or n.get("type") or "image").lower()
        n["layout"] = _clamp_box(
            _merge_preset(
                VISUAL_800_CROP_LAYOUT,
                n.get("layout") if isinstance(n.get("layout"), dict) else {},
            ),
            visual=True,
        )
        n["layout"]["height"] = 800
        n["layout"]["fit"] = "cover"
        n["animation"] = allowed_animation(n.get("animation") if isinstance(n.get("animation"), dict) else {"type": "none"}, creativity_level)
        n["transition_in"] = allowed_transition(n.get("transition_in") if isinstance(n.get("transition_in"), dict) else {}, creativity_level)
        n["transition_out"] = allowed_transition(n.get("transition_out") if isinstance(n.get("transition_out"), dict) else {}, creativity_level)
        out.append(n)
    return out


def _apply_presets_to_segment(
    obj: dict[str, Any],
    creativity_level: int,
    warnings: list[str],
    *,
    use_preset_backgrounds: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    has_visual = any(isinstance(v, dict) and str(v.get("element_id") or v.get("source_ref") or "").strip() for v in obj.get("visual_timeline", []) if isinstance(obj.get("visual_timeline"), list))
    names = _segment_preset_bundle(obj)
    if not _has_any_preset_name(names):
        names = _fallback_preset_names(obj, creativity_level, has_visual)
        warnings.append(f"fallback_refiner_preset_bundle:{names.get('preset_bundle')}")
    bundle = _bundle_with_safe_fallback(obj, names, creativity_level, has_visual, warnings)
    caption_layout_default = bundle["caption_layout"] or {"x": 90, "y": 1450, "width": 900, "height": 300, "z_index": 10}
    visual_layout_default = bundle["visual_layout"] or dict(VISUAL_800_CROP_LAYOUT)
    if creativity_level <= 0:
        background_default = resolve_refiner_preset_bundle({"background_preset": "black_reel_canvas"})["background"]
        caption_style_default = resolve_refiner_preset_bundle({"caption_preset": "bottom_subtitle_clean"})["caption_style"]
        visual_layout_default = dict(VISUAL_800_CROP_LAYOUT)
        caption_layout_default = resolve_refiner_preset_bundle({"caption_layout_preset": "caption_bottom_safe" if has_visual else "caption_only_center"})["caption_layout"]
    else:
        background_default = bundle["background"]
        caption_style_default = bundle["caption_style"]

    backgrounds: list[dict[str, Any]] = []
    for row in obj.get("background_timeline", []) if isinstance(obj.get("background_timeline"), list) else []:
        if isinstance(row, dict):
            base = _row_background_base(row, background_default)
            raw = _without_helper_keys(row)
            override = row.get("override") if isinstance(row.get("override"), dict) else {}
            bg = _merge_preset(_merge_preset(base, raw), override)
            backgrounds.append(
                _apply_preset_background_image(
                    bg,
                    obj,
                    use_preset_backgrounds=use_preset_backgrounds,
                    has_visual=has_visual,
                    creativity_level=creativity_level,
                    warnings=warnings,
                )
            )
    if not backgrounds and background_default:
        ts = float(obj.get("t_start", 0.0) or 0.0)
        te = float(obj.get("t_end", ts) or ts)
        bg = dict(background_default)
        bg.update({"t_start": ts, "t_end": te, "reason": f"preset:{bundle['names'].get('background_preset', '')}"})
        backgrounds.append(
            _apply_preset_background_image(
                bg,
                obj,
                use_preset_backgrounds=use_preset_backgrounds,
                has_visual=has_visual,
                creativity_level=creativity_level,
                warnings=warnings,
            )
        )

    captions: list[dict[str, Any]] = []
    for row in obj.get("caption_timeline", []) if isinstance(obj.get("caption_timeline"), list) else []:
        if not isinstance(row, dict):
            continue
        n = dict(row)
        raw_layout = n.get("layout") if isinstance(n.get("layout"), dict) else {}
        layout_override = n.get("layout_override") if isinstance(n.get("layout_override"), dict) else {}
        raw_style = n.get("style") if isinstance(n.get("style"), dict) else {}
        style_override = n.get("style_override") if isinstance(n.get("style_override"), dict) else {}
        raw_anim = n.get("animation") if isinstance(n.get("animation"), dict) else {}
        animation_override = n.get("animation_override") if isinstance(n.get("animation_override"), dict) else {}
        layout_base = _row_layout_base(n, "caption_layout_preset", caption_layout_default)
        style_base = _row_caption_style_base(n, caption_style_default)
        animation_base = _row_animation_base(n, "caption_animation_preset", bundle["caption_animation"])
        n["layout"] = _clamp_box(_merge_preset(_merge_preset(layout_base, raw_layout), layout_override))
        n["style"] = _merge_preset(_merge_preset(style_base, raw_style), style_override)
        n["animation"] = _merge_preset(_merge_preset(animation_base, raw_anim), animation_override)
        if caption_style_default or bundle["caption_animation"]:
            n["_preset_resolved"] = True
        captions.append(n)

    visuals: list[dict[str, Any]] = []
    for row in obj.get("visual_timeline", []) if isinstance(obj.get("visual_timeline"), list) else []:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("element_id") or row.get("source_ref") or "").strip()
        if not eid:
            warnings.append("drop_empty_visual_item")
            continue
        n = dict(row)
        raw_layout = n.get("layout") if isinstance(n.get("layout"), dict) else {}
        layout_override = n.get("layout_override") if isinstance(n.get("layout_override"), dict) else {}
        raw_anim = n.get("animation") if isinstance(n.get("animation"), dict) else {}
        animation_override = n.get("animation_override") if isinstance(n.get("animation_override"), dict) else {}
        visual_layout_base = _row_layout_base(n, "visual_layout_preset", visual_layout_default)
        visual_animation_base = _row_animation_base(n, "visual_animation_preset", bundle["visual_animation"])
        transition_base = _row_transition_base(n, bundle["transition"])
        n["layout"] = _clamp_box(_merge_preset(_merge_preset(visual_layout_base, raw_layout), layout_override), visual=True)
        n["layout"]["height"] = min(800, float(n["layout"].get("height", 800) or 800))
        n["layout"]["fit"] = "cover"
        n["animation"] = _merge_preset(_merge_preset(visual_animation_base, raw_anim), animation_override)
        if transition_base:
            n["transition_in"] = _merge_preset(transition_base, n.get("transition_in") if isinstance(n.get("transition_in"), dict) else {})
            n["transition_out"] = _merge_preset(transition_base, n.get("transition_out") if isinstance(n.get("transition_out"), dict) else {})
        visuals.append(n)
    if str(obj.get("media_id") or "").strip() == "" and any("caption_only_unmatched_from_media_json" in str(w) for w in obj.get("warnings", [])):
        visuals = []
    return {"background_timeline": backgrounds, "caption_timeline": captions, "visual_timeline": visuals}


def _normalize_captions(captions: list[dict[str, Any]], visuals: list[dict[str, Any]], creativity_level: int, warnings: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, c in enumerate(captions):
        n = dict(c)
        cs = float(n.get("t_start", 0.0) or 0.0)
        ce = float(n.get("t_end", 0.0) or 0.0)
        visual_active = any(_overlaps(cs, ce, float(v.get("t_start", 0.0) or 0.0), float(v.get("t_end", 0.0) or 0.0)) for v in visuals)
        n["layout"] = normalize_caption_layout(n.get("layout") if isinstance(n.get("layout"), dict) else {}, creativity_level, visual_active, warnings)
        seed = int(float(n.get("caption_group_index", idx) or idx)) + idx
        if creativity_level >= 2:
            if n.get("_preset_resolved"):
                n["style"] = normalize_caption_style(n.get("style") if isinstance(n.get("style"), dict) else {}, creativity_level, warnings)
                n["animation"] = allowed_animation(n.get("animation") if isinstance(n.get("animation"), dict) else {"type": "word_reveal", "intensity": "medium"}, creativity_level)
            else:
                n["style"] = creative_caption_style(seed, creativity_level, n.get("style") if isinstance(n.get("style"), dict) else {})
                n["animation"] = creative_caption_animation(seed, creativity_level, n.get("animation") if isinstance(n.get("animation"), dict) else {})
        else:
            n["style"] = normalize_caption_style(n.get("style") if isinstance(n.get("style"), dict) else {}, creativity_level, warnings)
            n["animation"] = allowed_animation(n.get("animation") if isinstance(n.get("animation"), dict) else {"type": "word_reveal", "intensity": "medium"}, creativity_level)
        n.pop("_preset_resolved", None)
        n.pop("_unmatched_caption_only", None)
        out.append(n)
    return out


def _normalize_backgrounds(backgrounds: list[dict[str, Any]], captions: list[dict[str, Any]], creativity_level: int) -> list[dict[str, Any]]:
    if creativity_level <= 1:
        return backgrounds
    out = list(backgrounds)
    if out:
        if creativity_level >= 3:
            has_preset_images = any(
                isinstance(row, dict)
                and str(row.get("background_image_preset") or row.get("source_path") or row.get("path") or "").strip()
                for row in out
            )
            if has_preset_images:
                return out
            signatures = {
                (
                    str(row.get("type") or ""),
                    str(row.get("color") or ""),
                    str(row.get("secondary_color") or ""),
                )
                for row in out
                if isinstance(row, dict)
            }
            generic = len(signatures) <= 1 and len(out) > 1
            if generic:
                varied: list[dict[str, Any]] = []
                for idx, row in enumerate(out):
                    ts = float(row.get("t_start", 0.0) or 0.0)
                    te = float(row.get("t_end", ts) or ts)
                    if te > ts:
                        varied.append(creative_background(idx, creativity_level, ts, te, "combiner_diversified_repeated_background"))
                return varied
        return out
    # Conservative refiner/fallback output often gives no design. Add subtle
    # per-caption dark backgrounds so creativity levels actually look different.
    for idx, c in enumerate(captions):
        ts = float(c.get("t_start", 0.0) or 0.0)
        te = float(c.get("t_end", ts) or ts)
        if te > ts:
            out.append(creative_background(idx, creativity_level, ts, te))
    return out


def _same_dict_subset(row: dict[str, Any], expected: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(row.get(k) == expected.get(k) for k in keys)


def _fixed_caption_layout_for(caption: dict[str, Any], visuals: list[dict[str, Any]]) -> dict[str, Any]:
    cs = float(caption.get("t_start", 0.0) or 0.0)
    ce = float(caption.get("t_end", 0.0) or 0.0)
    visual_active = any(
        _overlaps(cs, ce, float(v.get("t_start", 0.0) or 0.0), float(v.get("t_end", 0.0) or 0.0))
        for v in visuals
    )
    return dict(BOTTOM_CAPTION_LAYOUT if visual_active else CENTER_CAPTION_LAYOUT)


def _black_background(duration: float) -> list[dict[str, Any]]:
    return [
        {
            "t_start": 0.0,
            "t_end": duration,
            "type": "solid",
            "color": "#000000",
            "secondary_color": "#000000",
            "opacity": 1.0,
            "reason": "creativity_policy:fixed_black_background",
        }
    ]


def _final_filter_by_creativity(
    *,
    backgrounds: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    visuals: list[dict[str, Any]],
    duration: float,
    creativity_level: int,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    report: dict[str, Any] = {
        "creativity_level": creativity_level,
        "backgrounds_before": len(backgrounds),
        "captions_before": len(captions),
        "visuals_before": len(visuals),
        "normalizations": [],
    }

    if creativity_level <= 1:
        if backgrounds != _black_background(duration):
            report["normalizations"].append("backgrounds_forced_to_black")
            warnings.append(f"creativity_{creativity_level}_backgrounds_forced_to_black")
        backgrounds = _black_background(duration)

    filtered_visuals: list[dict[str, Any]] = []
    for idx, visual in enumerate(visuals):
        n = dict(visual)
        layout = n.get("layout") if isinstance(n.get("layout"), dict) else {}
        if creativity_level <= 4 and not _same_dict_subset(layout, VISUAL_800_CROP_LAYOUT, ("x", "y", "width", "height", "fit")):
            report["normalizations"].append(f"visual_layout_fixed:{idx}")
            warnings.append(f"creativity_{creativity_level}_visual_layout_final_fixed:{idx}")
        if creativity_level <= 4:
            n["layout"] = dict(VISUAL_800_CROP_LAYOUT)
        else:
            n["layout"] = _clamp_box(
                _merge_preset(VISUAL_800_CROP_LAYOUT, n.get("layout") if isinstance(n.get("layout"), dict) else {}),
                visual=True,
            )
            n["layout"]["height"] = min(800, float(n["layout"].get("height", 800) or 800))
            n["layout"]["fit"] = "cover"
        if creativity_level <= 2:
            if (n.get("animation") or {}).get("type") != "none":
                report["normalizations"].append(f"visual_animation_removed:{idx}")
            n["animation"] = {"type": "none", "intensity": "low"}
        else:
            n["animation"] = allowed_animation(n.get("animation") if isinstance(n.get("animation"), dict) else {}, creativity_level)
        n["transition_in"] = allowed_transition(n.get("transition_in") if isinstance(n.get("transition_in"), dict) else {}, creativity_level)
        n["transition_out"] = allowed_transition(n.get("transition_out") if isinstance(n.get("transition_out"), dict) else {}, creativity_level)
        filtered_visuals.append(n)
    visuals = filtered_visuals

    filtered_captions: list[dict[str, Any]] = []
    for idx, caption in enumerate(captions):
        n = dict(caption)
        if creativity_level <= 2:
            fixed_layout = _fixed_caption_layout_for(n, visuals)
            layout = n.get("layout") if isinstance(n.get("layout"), dict) else {}
            if not _same_dict_subset(layout, fixed_layout, ("x", "y", "width", "height")):
                report["normalizations"].append(f"caption_layout_fixed:{idx}")
                warnings.append(f"creativity_{creativity_level}_caption_layout_final_fixed:{idx}")
            n["layout"] = fixed_layout
        else:
            cs = float(n.get("t_start", 0.0) or 0.0)
            ce = float(n.get("t_end", 0.0) or 0.0)
            visual_active = any(
                _overlaps(cs, ce, float(v.get("t_start", 0.0) or 0.0), float(v.get("t_end", 0.0) or 0.0))
                for v in visuals
            )
            n["layout"] = normalize_caption_layout(n.get("layout") if isinstance(n.get("layout"), dict) else {}, creativity_level, visual_active, warnings)

        if creativity_level <= 2:
            if n.get("style") != DEFAULT_CAPTION_STYLE:
                report["normalizations"].append(f"caption_style_fixed:{idx}")
                warnings.append(f"creativity_{creativity_level}_caption_style_final_fixed:{idx}")
            n["style"] = dict(DEFAULT_CAPTION_STYLE)
        else:
            n["style"] = normalize_caption_style(n.get("style") if isinstance(n.get("style"), dict) else {}, creativity_level, warnings)

        if creativity_level <= 2:
            if (n.get("animation") or {}).get("type") != "word_reveal":
                report["normalizations"].append(f"caption_animation_fixed:{idx}")
            n["animation"] = {"type": "word_reveal", "intensity": "medium"}
        else:
            n["animation"] = allowed_animation(n.get("animation") if isinstance(n.get("animation"), dict) else {}, creativity_level)
        filtered_captions.append(n)
    captions = filtered_captions

    report["backgrounds_after"] = len(backgrounds)
    report["captions_after"] = len(captions)
    report["visuals_after"] = len(visuals)
    report["normalization_count"] = len(report["normalizations"])
    return backgrounds, captions, visuals, report


def _cross_check_inter(
    *,
    backgrounds: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    visuals: list[dict[str, Any]],
    duration: float,
    creativity_level: int,
) -> dict[str, Any]:
    issues: list[str] = []
    if creativity_level <= 1:
        for idx, bg in enumerate(backgrounds):
            if bg.get("type") != "solid" or str(bg.get("color")).lower() != "#000000":
                issues.append(f"level_{creativity_level}_non_black_background:{idx}")
    for idx, caption in enumerate(captions):
        ts = _safe_float(caption.get("t_start"))
        te = _safe_float(caption.get("t_end"))
        if ts is None or te is None or te <= ts:
            issues.append(f"invalid_caption_timing:{idx}")
        layout = caption.get("layout") if isinstance(caption.get("layout"), dict) else {}
        if float(layout.get("x", 0) or 0) < 0 or float(layout.get("y", 0) or 0) < 0:
            issues.append(f"caption_outside_canvas:{idx}")
    for idx, visual in enumerate(visuals):
        ts = _safe_float(visual.get("t_start"))
        te = _safe_float(visual.get("t_end"))
        if ts is None or te is None or te <= ts:
            issues.append(f"invalid_visual_timing:{idx}")
        if creativity_level <= 4:
            layout = visual.get("layout") if isinstance(visual.get("layout"), dict) else {}
            if not _same_dict_subset(layout, VISUAL_800_CROP_LAYOUT, ("x", "y", "width", "height", "fit")):
                issues.append(f"visual_layout_exceeds_policy:{idx}")
    return {
        "duration": duration,
        "creativity_level": creativity_level,
        "issues": issues,
        "passed": not issues,
    }


def generate_inter_from_refined_segments(
    refined_segments_dir: str | Path,
    media_json_path: str | Path,
    output_inter_path: str | Path,
    creativity_level: int = 2,
    use_preset_backgrounds: bool = True,
    render_captions: bool = True,
) -> Path:
    policy = get_creativity_policy(creativity_level)
    media_json = json.loads(Path(media_json_path).read_text(encoding="utf-8-sig"))
    warnings: list[str] = []
    backgrounds: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    visuals_raw: list[dict[str, Any]] = []

    for p in _iter_refined_files(Path(refined_segments_dir)):
        obj = parse_jsonish_file(p)
        if not isinstance(obj, dict):
            warnings.append(f"skip_unparseable_refined_segment:{p.name}")
            continue
        source_path = _source_segment_path_for_refined(p)
        source_segment = parse_jsonish_file(source_path) if source_path else None
        source_warnings = set(source_segment.get("warnings") or []) if isinstance(source_segment, dict) else set()
        is_unmatched_caption_only_segment = "caption_only_unmatched_from_media_json" in source_warnings
        obj = _repair_caption_timing_from_source(obj, source_segment if isinstance(source_segment, dict) else None, warnings)
        obj = {**obj, **_apply_presets_to_segment(obj, creativity_level, warnings, use_preset_backgrounds=use_preset_backgrounds)}
        if is_unmatched_caption_only_segment and isinstance(obj.get("caption_timeline"), list):
            for caption_row in obj["caption_timeline"]:
                if isinstance(caption_row, dict):
                    caption_row["_unmatched_caption_only"] = True
        for key, target in (
            ("background_timeline", backgrounds),
            ("caption_timeline", captions),
            ("visual_timeline", visuals_raw),
        ):
            rows = obj.get(key)
            if isinstance(rows, list):
                target.extend([r for r in rows if isinstance(r, dict)])

    backgrounds = _dedupe_backgrounds(backgrounds)
    captions = _dedupe_captions(captions)
    visuals_raw = _dedupe_visuals(visuals_raw)
    if not render_captions:
        before_fill = len(visuals_raw)
        visuals_raw = _fill_no_caption_visual_gaps(
            disabled_captions=captions,
            visuals_raw=visuals_raw,
            media_json=media_json,
            warnings=warnings,
        )
        visuals_raw = _dedupe_visuals(visuals_raw)
        filled = len(visuals_raw) - before_fill
        warnings.append(f"no_caption_unmatched_text_media_pairing:{filled}")
    backgrounds.sort(key=lambda x: (float(x.get("t_start", 0.0) or 0.0), float(x.get("t_end", 0.0) or 0.0)))
    captions.sort(key=lambda x: (float(x.get("t_start", 0.0) or 0.0), float(x.get("t_end", 0.0) or 0.0)))
    visuals_raw.sort(key=lambda x: (float(x.get("t_start", 0.0) or 0.0), float(x.get("t_end", 0.0) or 0.0)))
    visuals = _resolve_visual_sources(visuals_raw, media_json, warnings, creativity_level)
    visuals = _resolve_visual_overlaps(visuals, warnings)
    if not render_captions:
        original_caption_count = len(captions)
        captions = _keep_only_caption_only_cues(captions, visuals, warnings)
        warnings.append(f"caption_render_mode:no_caption_keeps_caption_only:{len(captions)}/{original_caption_count}")
    captions = _normalize_captions(captions, visuals, creativity_level, warnings)
    backgrounds = _normalize_backgrounds(backgrounds, captions, creativity_level)

    caption_end = max([float(c.get("t_end", 0.0) or 0.0) for c in captions], default=0.0)
    visual_end = max([float(v.get("t_end", 0.0) or 0.0) for v in visuals], default=0.0)
    audio_id, audio_path, audio_duration = main_audio(media_json)
    base_video_id, base_video_path, base_video_duration = main_video(media_json)
    main_visual_duration = _main_visual_duration(media_json)
    use_base_video = _should_use_base_video(media_json, base_video_id, audio_id)
    if audio_id and audio_path and audio_duration > 0:
        duration_source = "main_audio"
        duration = round(audio_duration, 3)
    elif use_base_video and base_video_id and base_video_path and base_video_duration > 0:
        duration_source = "main_video"
        duration = round(base_video_duration, 3)
    elif main_visual_duration > 0:
        duration_source = "main_visual"
        duration = round(main_visual_duration, 3)
    else:
        duration_source = "timeline"
        duration = round(max(caption_end, visual_end), 3)
    warnings.append(f"duration_source:{duration_source}:{duration:.3f}")
    backgrounds = _clamp_rows_to_duration(backgrounds, duration, "background", warnings)
    captions = _clamp_rows_to_duration(captions, duration, "caption", warnings)
    visuals = _clamp_rows_to_duration(visuals, duration, "visual", warnings)
    visuals = _resolve_visual_overlaps(visuals, warnings)
    backgrounds, captions, visuals, final_filter_report = _final_filter_by_creativity(
        backgrounds=backgrounds,
        captions=captions,
        visuals=visuals,
        duration=duration,
        creativity_level=creativity_level,
        warnings=warnings,
    )
    cross_check_report = _cross_check_inter(
        backgrounds=backgrounds,
        captions=captions,
        visuals=visuals,
        duration=duration,
        creativity_level=creativity_level,
    )
    print(
        "[A2V_V3] creativity final filter: "
        f"level={creativity_level}, normalizations={final_filter_report['normalization_count']}, "
        f"cross_check_passed={cross_check_report['passed']}"
    )
    if cross_check_report["issues"]:
        print("[A2V_V3] creativity cross-check issues: " + "; ".join(cross_check_report["issues"]))
        warnings.extend(cross_check_report["issues"])

    audio = None
    if audio_id and audio_path:
        audio = InterAudio(element_id=audio_id, source_path=audio_path, t_start=0.0, t_end=duration, volume=1.0)
    elif use_base_video and base_video_id and base_video_path:
        audio = InterAudio(element_id=base_video_id, source_path=base_video_path, t_start=0.0, t_end=duration, volume=1.0)

    inter = InterV3(
        canvas=InterCanvas(duration=duration),
        background_timeline=backgrounds,
        caption_timeline=captions,
        visual_timeline=visuals,
        audio=audio,
        warnings=warnings,
    )
    obj = inter.model_dump()
    if use_base_video and base_video_id and base_video_path:
        obj["base_visual"] = {
            "element_id": base_video_id,
            "source_ref": base_video_id,
            "source_path": base_video_path,
            "type": "video",
            "t_start": 0.0,
            "t_end": duration,
            "layout": {
                "x": 0,
                "y": 544,
                "width": 1080,
                "height": 800,
                "z_index": 1,
                "opacity": 1.0,
                "fit": "cover",
                "caption_safe": True,
            },
            "reason": "main_video_continuous_base_layer",
        }
        obj["warnings"].append(f"base_visual_from_main_video:{base_video_id}")
    obj["creativity_level"] = creativity_level
    obj["style_policy"] = {k: v for k, v in policy.items() if k != "rules_text"}
    obj["creativity_final_filter_report"] = final_filter_report
    obj["creativity_cross_check_report"] = cross_check_report
    out_path = write_json(output_inter_path, obj)
    report_path = Path(output_inter_path).with_name("creativity_final_filter_report.json")
    write_json(report_path, {"final_filter": final_filter_report, "cross_check": cross_check_report})
    return out_path
