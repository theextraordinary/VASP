from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from vasp.render.element_renderer import render_from_json

def _dedupe_visual_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Preserve refiner intent but remove exact duplicate visual actions.
    Does NOT remove intentional overlaps between different media.
    """
    seen: set[tuple[str, float, float, float, float, float, float]] = set()
    out: list[dict[str, Any]] = []

    for r in sorted(rows, key=lambda x: (float(x.get("t_start", 0.0) or 0.0), float(x.get("t_end", 0.0) or 0.0))):
        layout = r.get("layout") if isinstance(r.get("layout"), dict) else {}

        try:
            key = (
                str(r.get("element_id")),
                round(float(r.get("t_start", 0.0) or 0.0), 3),
                round(float(r.get("t_end", 0.0) or 0.0), 3),
                round(float(layout.get("x", 0.0) or 0.0), 2),
                round(float(layout.get("y", 0.0) or 0.0), 2),
                round(float(layout.get("width", 0.0) or 0.0), 2),
                round(float(layout.get("height", 0.0) or 0.0), 2),
            )
        except Exception:
            continue

        if key in seen:
            continue

        seen.add(key)
        out.append(r)

    return out


def _resolve_overlapping_visual_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    If two visuals overlap, split overlap in half and sequence them so they do not overlap.
    Operates on a flat list of visual rows with t_start/t_end.
    """
    items: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            ts = float(r.get("t_start", 0.0) or 0.0)
            te = float(r.get("t_end", ts) or ts)
        except Exception:
            continue
        if te <= ts:
            continue
        c = dict(r)
        c["t_start"] = ts
        c["t_end"] = te
        items.append(c)
    items.sort(key=lambda x: (x["t_start"], x["t_end"]))
    if len(items) < 2:
        return items

    # Handoff rule:
    # if later visual starts while earlier one is active, cut earlier at later.t_start.
    # Example: A 0-12, B 5-12 => A 0-5, B 5-12.
    for i in range(1, len(items)):
        cur = items[i]
        cs = float(cur["t_start"])
        for j in range(i):
            prev = items[j]
            ps, pe = float(prev["t_start"]), float(prev["t_end"])
            if ps < cs < pe:
                prev["t_end"] = round(cs, 3)

    out = [x for x in items if float(x["t_end"]) - float(x["t_start"]) > 1e-3]
    out.sort(key=lambda x: (x["t_start"], x["t_end"]))
    return out


def _norm_path_key(p: str) -> str:
    return str(p or "").replace("\\", "/").strip().lower()


def _resolve_source_ref_to_id(
    src_ref: str,
    *,
    by_id: dict[str, dict[str, Any]],
    by_path: dict[str, str],
) -> str | None:
    # Direct media id first.
    if src_ref in by_id:
        return src_ref
    k = _norm_path_key(src_ref)
    if k in by_path:
        return by_path[k]
    # Fallback by basename when absolute/relative path shapes differ.
    base = Path(k).name
    if base:
        for pkey, eid in by_path.items():
            if Path(pkey).name == base:
                return eid
    return None

def render_segment_outputs_to_video(
    *,
    segment_outputs_dir: str | Path,
    media_json_path: str | Path,
    word_map_all_path: str | Path | None = None,
    output_inter_path: str | Path = "output/inter_from_segment_outputs.json",
    output_video_path: str | Path = "output/a2v_video_from_segment_outputs.mp4",
    use_old_renderer: bool = True,
) -> tuple[Path, Path]:
    """Merge per-segment refiner outputs into one inter.json and render it."""
    sdir = Path(segment_outputs_dir)
    media_path = Path(media_json_path)
    inter_path = Path(output_inter_path)
    video_path = Path(output_video_path)
    debug_dir = inter_path.parent / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    if not sdir.exists():
        raise FileNotFoundError(f"segment outputs dir not found: {sdir}")
    if not media_path.exists():
        raise FileNotFoundError(f"media json not found: {media_path}")

    media_json = json.loads(media_path.read_text(encoding="utf-8"))
    media_inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    grouped_caption_map = _extract_grouped_caption_map(media_json)

    by_id: dict[str, dict[str, Any]] = {}
    by_path: dict[str, str] = {}
    for row in media_inputs:
        if isinstance(row, dict) and row.get("id"):
            eid = str(row["id"])
            by_id[eid] = row
            p = _norm_path_key(str(row.get("path", "")))
            if p:
                by_path[p] = eid

    seg_files = sorted(sdir.glob("refiner_segment_output_*.txt"))
    if not seg_files:
        raise FileNotFoundError(f"No segment output txt files found in {sdir}")
    print(f"[A2V_PIPELINE][RENDER] segment files: {len(seg_files)}")

    prompt_segments = _load_segment_objects_from_prompts(sdir.parent / "refiner_segment_prompts")

    parsed_segments: list[dict[str, Any]] = []
    visual_rows_raw: list[dict[str, Any]] = []
    caption_policy_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    canvas = {"width": 1080, "height": 1920, "fps": 30, "duration": 30.0}
    invalid_segment_count = 0
    skipped_invalid_visuals = 0

    for idx, p in enumerate(seg_files, start=1):
        obj = _parse_refiner_segment_with_fallback(p, debug_dir=debug_dir)
        if obj is None:
            invalid_segment_count += 1
            warnings.append(f"invalid_segment_json_skipped:{p.name}")
            continue
        parsed_segments.append({"file": str(p).replace("\\", "/"), "data": obj, "index": idx})
        cv = obj.get("canvas")
        if isinstance(cv, dict):
            canvas["width"] = int(float(cv.get("width", canvas["width"]) or canvas["width"]))
            canvas["height"] = int(float(cv.get("height", canvas["height"]) or canvas["height"]))
            canvas["fps"] = int(float(cv.get("fps", canvas["fps"]) or canvas["fps"]))
            canvas["duration"] = max(float(canvas["duration"]), float(cv.get("duration", 0.0) or 0.0))

        timeline = obj.get("visual_timeline")
        if not isinstance(timeline, list):
            timeline = obj.get("final_timeline")
        if not isinstance(timeline, list):
            warnings.append(f"malformed_visual_timeline_skipped:{p.name}")
            continue
        for row in timeline:
            if isinstance(row, dict):
                visual_rows_raw.append(dict(row))
            else:
                skipped_invalid_visuals += 1
                warnings.append(f"invalid_visual_row_skipped:{p.name}")

        caption_policy = _normalize_refiner_caption_policy(obj)
        caption_policy_rows.append(
            {
                "index": idx,
                "file": str(p).replace("\\", "/"),
                "policy": caption_policy,
                "segment_obj": prompt_segments.get(idx),
                "obj": obj,
            }
        )

    _write_debug_json(debug_dir / "parsed_refiner_segments.json", parsed_segments)

    target_duration = _resolve_target_duration(media_json, by_id, probe, fallback=float(canvas["duration"]))
    canvas["duration"] = target_duration

    normalized_visual_rows: list[dict[str, Any]] = []
    for row in visual_rows_raw:
        src_ref = str(row.get("source_ref") or row.get("element_id") or "").strip()
        if not src_ref:
            skipped_invalid_visuals += 1
            warnings.append("visual_missing_source_skipped")
            continue
        resolved_id = _resolve_source_ref_to_id(src_ref, by_id=by_id, by_path=by_path)
        if not resolved_id:
            raise ValueError(f"visual source_ref {src_ref} not found in media.json")
        media_type = str(by_id[resolved_id].get("media_type", "")).strip().lower()
        if "audio" in media_type or "caption" in media_type:
            skipped_invalid_visuals += 1
            warnings.append(f"skip_non_visual_source:{resolved_id}")
            continue
        layout = row.get("layout")
        if not isinstance(layout, dict):
            skipped_invalid_visuals += 1
            warnings.append(f"visual_missing_layout_skipped:{src_ref}")
            continue
        ts = _clamp_time(_to_float(row.get("t_start"), 0.0), target_duration)
        te = _clamp_time(_to_float(row.get("t_end"), ts), target_duration)
        if te <= ts:
            skipped_invalid_visuals += 1
            warnings.append(f"visual_invalid_time_skipped:{src_ref}:{ts}-{te}")
            continue
        mt = _normalize_refiner_media_type(str(row.get("type", "")), by_id[resolved_id].get("path"))
        n = dict(row)
        n["element_id"] = resolved_id
        n["source_ref"] = resolved_id
        n["_norm_media_type"] = mt
        n["t_start"] = round(ts, 3)
        n["t_end"] = round(te, 3)
        normalized_visual_rows.append(n)

    normalized_visual_rows = _dedupe_visual_rows(normalized_visual_rows)
    normalized_visual_rows = _normalize_visual_timeline_one_at_a_time(normalized_visual_rows, warnings)
    _write_debug_json(debug_dir / "normalized_visual_rows.json", normalized_visual_rows)

    elements: list[dict[str, Any]] = []
    audio_id = _pick_first_audio_id(by_id)
    if audio_id:
        audio_row = by_id[audio_id]
        volume = _to_float(audio_row.get("volume"), 1.0)
        elements.append(
            {
                "element_id": audio_id,
                "type": "music",
                "timing": {"start": 0.0, "duration": round(target_duration, 3)},
                "properties": {
                    "type": "music",
                    "source_uri": audio_row.get("path"),
                    "timing": {"start": 0.0, "duration": round(target_duration, 3)},
                },
                "actions": [{"t_start": 0.0, "t_end": round(target_duration, 3), "op": "play", "params": {"volume": volume}}],
            }
        )

    by_visual_id: dict[str, list[dict[str, Any]]] = {}
    for r in normalized_visual_rows:
        by_visual_id.setdefault(str(r["element_id"]), []).append(r)

    visual_action_count = 0
    for eid, rows in by_visual_id.items():
        rows = sorted(rows, key=lambda r: (r["t_start"], r["t_end"]))
        src = by_id[eid]
        probe_row = probe.get(eid) if isinstance(probe, dict) else None
        src_w, src_h = _probe_size(probe_row)
        src_path = src.get("path")

        etype = rows[0].get("_norm_media_type", "image")
        renderer_type = "gif" if etype == "gif" else ("video" if etype == "video" else "image")
        actions: list[dict[str, Any]] = []
        min_start = rows[0]["t_start"]
        max_end = rows[0]["t_end"]
        for r in rows:
            ts = float(r["t_start"])
            te = float(r["t_end"])
            min_start = min(min_start, ts)
            max_end = max(max_end, te)
            layout = r.get("layout") if isinstance(r.get("layout"), dict) else {}
            lw = max(1.0, _to_float(layout.get("width"), float(src_w)))
            lh = max(1.0, _to_float(layout.get("height"), float(src_h)))
            lx = _to_float(layout.get("x"), 0.0)
            ly = _to_float(layout.get("y"), 0.0)
            cw, ch = float(canvas["width"]), float(canvas["height"])
            lw = min(lw, cw)
            lh = min(lh, ch)
            lx = max(0.0, min(lx, cw - lw))
            ly = max(0.0, min(ly, ch - lh))
            cx = lx + lw / 2.0
            cy = ly + lh / 2.0
            fit = str(layout.get("fit") or "contain").lower()
            scale = _compute_scale_with_fit(src_w=src_w, src_h=src_h, target_w=lw, target_h=lh, fit=fit, explicit_scale=None)
            opacity = _to_float(layout.get("opacity"), 1.0)
            opacity = max(0.0, min(1.0, opacity))
            tin = r.get("transition_in") if isinstance(r.get("transition_in"), dict) else {}
            tout = r.get("transition_out") if isinstance(r.get("transition_out"), dict) else {}
            actions.append(
                {
                    "t_start": round(ts, 3),
                    "t_end": round(te, 3),
                    "op": "show",
                    "params": _drop_nones(
                        {
                            "x": round(cx, 3),
                            "y": round(cy, 3),
                            "from_x": round(cx, 3),
                            "from_y": round(cy, 3),
                            "scale": round(scale, 6),
                            "motion_ease": "linear",
                            "trim_in": 0.0,
                            "trim_out": round(max(0.0, te - ts), 3),
                            "fade_in_s": _transition_to_fade_seconds(tin),
                            "fade_out_s": _transition_to_fade_seconds(tout),
                            "alpha": opacity,
                        }
                    ),
                }
            )
            visual_action_count += 1
        elements.append(
            {
                "element_id": eid,
                "type": renderer_type,
                "timing": {"start": round(min_start, 3), "duration": round(max_end - min_start, 3)},
                "properties": {
                    "type": renderer_type,
                    "source_uri": src_path,
                    "timing": {"start": round(min_start, 3), "duration": round(max_end - min_start, 3)},
                },
                "actions": actions,
            }
        )

    # Caption actions are generated from grouped_caption_map + segment mapping.
    visual_intervals = _collect_visual_intervals(elements)
    caption_actions_raw: list[dict[str, Any]] = []
    for row in caption_policy_rows:
        seg_obj = row.get("segment_obj") if isinstance(row.get("segment_obj"), dict) else None
        obj = row.get("obj") if isinstance(row.get("obj"), dict) else {}
        policy = row.get("policy") if isinstance(row.get("policy"), dict) else {}
        groups = _caption_groups_for_segment(grouped_caption_map, seg_obj, obj=obj)
        groups = sorted(groups, key=lambda g: (_to_float(g.get("start"), 0.0), _to_float(g.get("end"), 0.0)))
        if not groups:
            continue
        style = _caption_style_from_policy(policy)
        animation = policy.get("animation") if isinstance(policy.get("animation"), dict) else {}
        for g in groups:
            layout = _caption_layout_for_group(g, visual_intervals, policy)
            action = _make_caption_action(g, layout, style, animation, _load_word_map_all(word_map_all_path))
            caption_actions_raw.append(action)

    caption_actions = _dedupe_caption_actions(caption_actions_raw)
    _write_debug_json(debug_dir / "normalized_caption_cues.json", caption_actions)

    if caption_actions:
        cap_start = min(float(a["t_start"]) for a in caption_actions)
        cap_end = max(float(a["t_end"]) for a in caption_actions)
        elements.append(
            {
                "element_id": "caption_track_1",
                "type": "caption",
                "timing": {"start": round(cap_start, 3), "duration": round(max(0.0, cap_end - cap_start), 3)},
                "properties": {
                    "type": "caption",
                    "timing": {"start": round(cap_start, 3), "duration": round(max(0.0, cap_end - cap_start), 3)},
                    "transform": {"x": 540.0, "y": 1600.0},
                    "font_family": "Inter",
                    "font_weight": "800",
                    "color": "#FFFFFF",
                    "stroke_color": "#000000",
                    "stroke_width": 3,
                },
                "actions": caption_actions,
            }
        )

    _clip_elements_to_duration(elements, target_duration)
    warnings.extend(_collect_screen_bg_parse_warnings(seg_files))
    _write_debug_json(debug_dir / "render_warnings.json", warnings)

    inter = {
        "version": "1.1",
        "video": {
            "size": {"width": int(canvas["width"]), "height": int(canvas["height"])},
            "fps": int(canvas["fps"]),
            "duration": round(target_duration, 3),
            "bg_color": [0, 0, 0],
            "output_path": str(video_path).replace("\\", "/"),
            "metadata": {
                "design_events": _collect_screen_bg_events(seg_files),
                "render_warnings": warnings,
            },
        },
        "properties_path": None,
        "elements": elements,
    }
    _verify_inter_or_raise(inter, has_audio=bool(audio_id), has_captions=bool(caption_actions))
    print(
        "[A2V_PIPELINE][RENDER] summary: "
        f"visual_actions={visual_action_count}, caption_actions={len(caption_actions)}, "
        f"skipped_invalid_visuals={skipped_invalid_visuals}, skipped_invalid_segment_json_files={invalid_segment_count}, "
        f"duration={round(target_duration,3)}, output={str(video_path).replace('\\','/')}"
    )

    inter_path.parent.mkdir(parents=True, exist_ok=True)
    inter_path.write_text(json.dumps(inter, ensure_ascii=False, indent=2), encoding="utf-8")
    if use_old_renderer:
        render_from_json(str(inter_path), strict=True)
    return inter_path, video_path


def _load_segment_json_from_text(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"```json\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        m = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1).strip())
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _parse_refiner_segment_or_raise(path: Path, *, debug_dir: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    repaired_text = _repair_json_brackets(text)
    if repaired_text != text:
        try:
            obj = json.loads(repaired_text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    fenced = _extract_fenced_json_block(text)
    if fenced is not None:
        try:
            obj = json.loads(fenced)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        repaired_fenced = _repair_json_brackets(fenced)
        if repaired_fenced != fenced:
            try:
                obj = json.loads(repaired_fenced)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    balanced = _extract_balanced_json_object(text)
    if balanced is not None:
        try:
            obj = json.loads(balanced)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        repaired_balanced = _repair_json_brackets(balanced)
        if repaired_balanced != balanced:
            try:
                obj = json.loads(repaired_balanced)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    dbg = debug_dir / f"{path.stem}_parse_error.txt"
    dbg.write_text(text, encoding="utf-8")
    raise ValueError(f"Could not parse refiner segment JSON: {path}")


def _parse_refiner_segment_with_fallback(path: Path, *, debug_dir: Path) -> dict[str, Any] | None:
    try:
        return _parse_refiner_segment_or_raise(path, debug_dir=debug_dir)
    except Exception:
        return None


def _extract_fenced_json_block(text: str) -> str | None:
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
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
                return text[begin : i + 1]
    return None


def _repair_json_brackets(text: str) -> str:
    out: list[str] = []
    stack: list[str] = []
    in_str = False
    esc = False
    pairs = {"{": "}", "[": "]"}
    for ch in text:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            continue
        if ch in "{[":
            stack.append(ch)
            out.append(ch)
            continue
        if ch in "}]":
            if stack:
                expected = pairs[stack[-1]]
                if ch == expected:
                    stack.pop()
                    out.append(ch)
                else:
                    # Replace mismatched closer with expected closer.
                    stack.pop()
                    out.append(expected)
            else:
                # Drop unmatched closer.
                continue
            continue
        out.append(ch)
    while stack:
        out.append(pairs[stack.pop()])
    return "".join(out)


def _extract_grouped_caption_map(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return []
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        groups = transcript.get("caption_groups")
        if not isinstance(groups, list):
            continue
        out: list[dict[str, Any]] = []
        for i, row in enumerate(groups):
            if not isinstance(row, dict):
                continue
            try:
                s = float(row.get("start"))
                e = float(row.get("end"))
            except Exception:
                continue
            out.append({"index": i, "text": str(row.get("text", "")).strip(), "start": round(s, 3), "end": round(e, 3)})
        return out
    return []


def _load_segment_objects_from_prompts(prompts_dir: Path) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    if not prompts_dir.exists():
        return out
    for p in sorted(prompts_dir.glob("refiner_segment_prompt_*.txt")):
        m = re.search(r"_(\d+)\.txt$", p.name)
        if not m:
            continue
        idx = int(m.group(1))
        txt = p.read_text(encoding="utf-8", errors="ignore")
        objs = _extract_all_balanced_json_objects(txt)
        seg_obj = None
        for obj_text in reversed(objs):
            try:
                obj = json.loads(obj_text)
            except Exception:
                continue
            if isinstance(obj, dict) and "segment_id" in obj and "t_start" in obj and "t_end" in obj:
                seg_obj = obj
                break
        if isinstance(seg_obj, dict):
            out[idx] = seg_obj
    return out


def _extract_all_balanced_json_objects(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        cand = _extract_balanced_json_object(text[i:])
        if not cand:
            i += 1
            continue
        out.append(cand)
        i += len(cand)
    return out


def _normalize_refiner_media_type(type_text: str, source_path: Any) -> str:
    t = str(type_text or "").strip().lower()
    src = str(source_path or "").strip().lower()
    if t in {"audio", "music", "sfx"}:
        return "audio"
    if t in {"video"} or "no audio video clips" in t:
        return "video"
    if t in {"gif"}:
        return "gif"
    if t in {"sticker"}:
        return "gif" if src.endswith(".gif") else "image"
    if t in {"image"}:
        return "image"
    if "gif" in t:
        return "gif"
    if "sticker" in t:
        return "gif" if src.endswith(".gif") else "image"
    if "image" in t:
        return "image"
    if "video" in t:
        return "video"
    if "audio" in t:
        return "audio"
    return "image"


def _normalize_refiner_caption_policy(obj: dict[str, Any]) -> dict[str, Any]:
    policy = obj.get("caption_render_policy")
    if isinstance(policy, dict):
        out = dict(policy)
    else:
        out = {}
    track = obj.get("caption_track") if isinstance(obj.get("caption_track"), dict) else {}
    if not out:
        out = {"source": "grouped_caption_map", "render_all_caption_groups_in_segment": True}
    if "style" not in out and isinstance(track.get("style"), dict):
        out["style"] = track.get("style")
    if "animation" not in out and isinstance(track.get("animation"), dict):
        out["animation"] = track.get("animation")
    if "with_visual_layout" not in out:
        layout = track.get("layout") if isinstance(track.get("layout"), dict) else {}
        out["with_visual_layout"] = layout or {"x": 90, "y": 1450, "width": 900, "height": 300, "z_index": 10}
    if "no_visual_layout" not in out:
        out["no_visual_layout"] = {"x": 120, "y": 820, "width": 840, "height": 300, "z_index": 10}
    return out


def _resolve_target_duration(
    media_json: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    probe: dict[str, Any],
    *,
    fallback: float,
) -> float:
    aid = _pick_first_audio_id(by_id)
    if aid:
        d = _probe_duration(probe.get(aid))
        if d <= 0.0:
            d = _probe_duration_from_path(by_id.get(aid, {}).get("path"))
        if d > 0:
            return d
    # Fallback to grouped captions span if available.
    gcm = _extract_grouped_caption_map(media_json)
    if gcm:
        starts = [_to_float(g.get("start"), 0.0) for g in gcm if isinstance(g, dict)]
        ends = [_to_float(g.get("end"), 0.0) for g in gcm if isinstance(g, dict)]
        if ends:
            return max(0.001, max(ends))
    return max(0.001, float(fallback))


def _caption_groups_for_segment(
    grouped_caption_map: list[dict[str, Any]],
    segment_obj: dict[str, Any] | None,
    *,
    obj: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(segment_obj, dict):
        idxs = segment_obj.get("caption_indices")
        if isinstance(idxs, list) and any(isinstance(x, int) for x in idxs):
            lookup = {int(r["index"]): r for r in grouped_caption_map if isinstance(r, dict) and isinstance(r.get("index"), int)}
            out = [lookup[i] for i in idxs if isinstance(i, int) and i in lookup]
            if out:
                return out
    # fallback overlap by segment window
    seg_start = None
    seg_end = None
    if isinstance(segment_obj, dict):
        seg_start = _to_float(segment_obj.get("t_start"), None)
        seg_end = _to_float(segment_obj.get("t_end"), None)
    if seg_start is None or seg_end is None:
        if isinstance(obj, dict):
            tl = obj.get("visual_timeline") if isinstance(obj.get("visual_timeline"), list) else obj.get("final_timeline")
            if isinstance(tl, list):
                ts = [_to_float(x.get("t_start"), None) for x in tl if isinstance(x, dict)]
                te = [_to_float(x.get("t_end"), None) for x in tl if isinstance(x, dict)]
                ts = [x for x in ts if x is not None]
                te = [x for x in te if x is not None]
                if ts and te:
                    seg_start, seg_end = min(ts), max(te)
    if seg_start is None or seg_end is None:
        return []
    out: list[dict[str, Any]] = []
    for g in grouped_caption_map:
        if not isinstance(g, dict):
            continue
        gs = _to_float(g.get("start"), None)
        ge = _to_float(g.get("end"), None)
        if gs is None or ge is None:
            continue
        if gs < seg_end and seg_start < ge:
            out.append(g)
    return out


def _caption_group_overlaps_visual(group: dict[str, Any], visual_intervals: list[tuple[float, float]]) -> bool:
    gs = _to_float(group.get("start"), 0.0)
    ge = _to_float(group.get("end"), gs)
    for vs, ve in visual_intervals:
        if vs < ge and gs < ve:
            return True
    return False


def _caption_layout_for_group(
    group: dict[str, Any],
    visual_intervals: list[tuple[float, float]],
    caption_policy: dict[str, Any],
) -> dict[str, Any]:
    with_layout = caption_policy.get("with_visual_layout") if isinstance(caption_policy.get("with_visual_layout"), dict) else {}
    no_layout = caption_policy.get("no_visual_layout") if isinstance(caption_policy.get("no_visual_layout"), dict) else {}
    if _caption_group_overlaps_visual(group, visual_intervals):
        return with_layout or {"x": 90, "y": 1450, "width": 900, "height": 300, "z_index": 10}
    return no_layout or {"x": 120, "y": 820, "width": 840, "height": 300, "z_index": 10}


def _caption_style_from_policy(caption_policy: dict[str, Any]) -> dict[str, Any]:
    style = caption_policy.get("style") if isinstance(caption_policy.get("style"), dict) else {}
    out = {
        "font_family": style.get("font_family", "Inter"),
        "font_size": style.get("font_size"),
        "font_size_rule": style.get("font_size_rule"),
        "font_weight": style.get("font_weight", "800"),
        "text_color": style.get("text_color", "#FFFFFF"),
        "highlight_color": style.get("highlight_color", "#FFD84D"),
        "background_color": style.get("background_color", "rgba(0,0,0,0.45)"),
    }
    return out


def _make_caption_action(
    group: dict[str, Any],
    layout: dict[str, Any],
    style: dict[str, Any],
    animation: dict[str, Any],
    word_map_all: list[dict[str, Any]],
) -> dict[str, Any]:
    text = str(group.get("text", "")).strip()
    ts = round(_to_float(group.get("start"), 0.0), 3)
    te = round(_to_float(group.get("end"), ts), 3)
    x = _to_float(layout.get("x"), 90.0)
    y = _to_float(layout.get("y"), 1450.0)
    w = _to_float(layout.get("width"), 900.0)
    h = _to_float(layout.get("height"), 300.0)
    cx = x + w / 2.0
    cy = y + h / 2.0
    fs = style.get("font_size")
    try:
        fsn = int(float(fs)) if fs is not None else _font_size_from_rule(text, style.get("font_size_rule"))
    except Exception:
        fsn = _font_size_from_rule(text, style.get("font_size_rule"))
    if fsn <= 1:
        fsn = _font_size_from_rule(text, style.get("font_size_rule"))
    bg = style.get("background_color")
    params = {
        "text": text,
        "caption_group_index": group.get("index"),
        "x": round(cx, 3),
        "y": round(cy, 3),
        "font_family": style.get("font_family", "Inter"),
        "font_size": max(2, int(fsn)),
        "font_weight": style.get("font_weight", "800"),
        "color": style.get("text_color", "#FFFFFF"),
        "highlight_color": style.get("highlight_color", "#FFD84D"),
        "stroke_color": "#000000",
        "stroke_width": 3,
        "caption_animation": str(animation.get("type", "fade")),
        "caption_mode": "line_simple",
        "background_opacity": _rgba_opacity(bg) if _rgba_opacity(bg) is not None else 0.45,
        "background_color": _rgba_color(bg) or "#000000",
    }
    return {"t_start": ts, "t_end": te, "op": "show", "params": params}


def _dedupe_caption_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[Any, dict[str, Any]] = {}
    for a in actions:
        params = a.get("params") if isinstance(a.get("params"), dict) else {}
        idx = params.get("caption_group_index")
        ts = round(_to_float(a.get("t_start"), 0.0), 3)
        te = round(_to_float(a.get("t_end"), ts), 3)
        txt = str(params.get("text", "")).strip()
        key = ("idx", idx) if isinstance(idx, int) else ("txt", txt, ts, te)
        old = best.get(key)
        if old is None:
            best[key] = a
        else:
            od = _to_float(old.get("t_end"), 0.0) - _to_float(old.get("t_start"), 0.0)
            nd = te - ts
            if nd > od:
                best[key] = a
    out = list(best.values())
    out.sort(key=lambda x: (_to_float(x.get("t_start"), 0.0), _to_float(x.get("t_end"), 0.0)))
    return out


def _clamp_time(v: float, duration: float) -> float:
    return max(0.0, min(float(v), float(duration)))


def _compute_scale_with_fit(
    *,
    src_w: int,
    src_h: int,
    target_w: float,
    target_h: float,
    fit: str,
    explicit_scale: float | None,
) -> float:
    if fit == "none":
        if explicit_scale is not None and explicit_scale > 0:
            return explicit_scale
        return 1.0
    return _compute_scale(src_w=src_w, src_h=src_h, target_w=target_w, target_h=target_h, fit=fit)


def _normalize_visual_timeline_one_at_a_time(rows: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    """
    General visual timeline normalizer for pipeline runs.

    Guarantees:
    - At most one visual is active at any given time.
    - Deterministic ordering by time.
    - Attempts to preserve all visuals by trimming/splitting instead of dropping.
    """
    items = sorted(
        rows,
        key=lambda x: (
            float(x.get("t_start", 0.0)),
            float(x.get("t_end", 0.0)),
        ),
    )
    i = 1
    while i < len(items):
        prev = items[i - 1]
        cur = items[i]
        ps = float(prev["t_start"])
        pe = float(prev["t_end"])
        cs = float(cur["t_start"])
        ce = float(cur["t_end"])
        if cs < pe:
            # Same-start overlap: keep earlier-ending clip first, move next to start after it.
            if abs(cs - ps) < 1e-6:
                cur["t_start"] = round(pe, 3)
                warnings.append(
                    f"overlap_shifted_same_start:{cur.get('element_id')} to {round(pe,3)}"
                )
                items.sort(key=lambda x: (float(x.get("t_start", 0.0)), float(x.get("t_end", 0.0))))
                i = 1
                continue
            else:
                # Trim previous to current start.
                original_prev_end = pe
                prev["t_end"] = round(cs, 3)
                warnings.append(
                    f"overlap_trimmed:{prev.get('element_id')}->{cur.get('element_id')} at {round(cs,3)}"
                )
                # If previous wraps the current clip, keep the remaining tail after current ends.
                if original_prev_end > ce:
                    tail = dict(prev)
                    tail["t_start"] = round(ce, 3)
                    tail["t_end"] = round(original_prev_end, 3)
                    items.insert(i + 1, tail)
                    warnings.append(
                        f"overlap_tail_created:{tail.get('element_id')} {round(ce,3)}-{round(original_prev_end,3)}"
                    )
                items.sort(key=lambda x: (float(x.get("t_start", 0.0)), float(x.get("t_end", 0.0))))
                i = 1
                continue
        i += 1

    out = []
    for r in sorted(items, key=lambda x: (float(x.get("t_start", 0.0)), float(x.get("t_end", 0.0)))):
        if float(r["t_end"]) <= float(r["t_start"]):
            warnings.append(f"dropped_zero_duration_visual:{r.get('element_id')}:{r.get('t_start')}-{r.get('t_end')}")
            continue
        out.append(r)
    return out


def _resolve_visual_overlaps_handoff(rows: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    # Backward-compatible alias.
    return _normalize_visual_timeline_one_at_a_time(rows, warnings)


def _caption_track_to_actions(
    *,
    caption_tracks: list[dict[str, Any]],
    grouped_lookup: dict[int, tuple[float, float, str]],
    visual_intervals: list[tuple[float, float]],
    canvas_w: int,
    canvas_h: int,
    segment_windows: list[tuple[float, float]],
) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    for row in caption_tracks:
        track = row.get("track")
        if not isinstance(track, dict):
            continue
        style = track.get("style") if isinstance(track.get("style"), dict) else {}
        layout = track.get("layout") if isinstance(track.get("layout"), dict) else {}
        anim = track.get("animation") if isinstance(track.get("animation"), dict) else {}
        cues = track.get("cues")
        if not isinstance(cues, list):
            raise ValueError("caption_track.cues malformed")
        for cue in cues:
            if not isinstance(cue, dict):
                raise ValueError("caption_track.cues malformed")
            idx = cue.get("index")
            txt = str(cue.get("text", "")).strip()
            if isinstance(idx, int) and idx in grouped_lookup and not txt:
                txt = grouped_lookup[idx][2]
            ts = _to_float(cue.get("t_start", cue.get("start")), 0.0)
            te = _to_float(cue.get("t_end", cue.get("end")), ts)
            if te <= ts:
                raise ValueError(f"caption cue invalid timing index={idx} ({ts}-{te})")
            cue_layout = cue.get("layout") if isinstance(cue.get("layout"), dict) else {}
            style_override = cue.get("style_override") if isinstance(cue.get("style_override"), dict) else {}
            style_eff = dict(style)
            style_eff.update(style_override)
            has_override_xy = ("x" in cue_layout and "y" in cue_layout) or ("x" in cue and "y" in cue)
            if has_override_xy:
                cx = _to_float(cue_layout.get("x", cue.get("x")), 540.0)
                cy = _to_float(cue_layout.get("y", cue.get("y")), 1600.0)
                cw = _to_float(cue_layout.get("width", layout.get("width")), 900.0)
                ch = _to_float(cue_layout.get("height", layout.get("height")), 300.0)
                cx = cx + cw / 2.0 if cx <= float(canvas_w) else cx
                cy = cy + ch / 2.0 if cy <= float(canvas_h) else cy
            else:
                if _has_visual_in_window(visual_intervals, ts, te):
                    cx, cy = 540.0, 1600.0
                else:
                    cx, cy = 540.0, 960.0
            fs = _extract_font_size(style_eff, txt)
            if fs is None or fs <= 1:
                fs = _font_size_from_rule(txt, style_eff.get("font_size_rule"))
            bg = style_eff.get("background_color")
            raw.append(
                {
                    "index": idx,
                    "t_start": round(ts, 3),
                    "t_end": round(te, 3),
                    "params": _drop_nones(
                        {
                            "text": txt,
                            "caption_group_index": idx,
                            "x": round(cx, 3),
                            "y": round(cy, 3),
                            "font_family": style_eff.get("font_family", "Inter"),
                            "font_size": max(2, int(fs)),
                            "font_weight": style_eff.get("font_weight", "800"),
                            "color": style_eff.get("text_color", "#FFFFFF"),
                            "highlight_color": style_eff.get("highlight_color", "#FFD84D"),
                            "stroke_color": "#000000",
                            "stroke_width": 3,
                            "caption_animation": str(anim.get("type", "word_reveal")),
                            "caption_mode": "line_simple",
                            "background_color": _rgba_color(bg) or "#000000",
                            "background_opacity": _rgba_opacity(bg) if _rgba_opacity(bg) is not None else 0.45,
                        }
                    ),
                }
            )

    if not raw and grouped_lookup and segment_windows:
        for ws, we in segment_windows:
            for idx, (s, e, txt) in grouped_lookup.items():
                if e <= ws or s >= we:
                    continue
                ts = max(ws, s)
                te = min(we, e)
                if te <= ts:
                    continue
                if _has_visual_in_window(visual_intervals, ts, te):
                    cx, cy = 540.0, 1600.0
                else:
                    cx, cy = 540.0, 960.0
                raw.append(
                    {
                        "index": idx,
                        "t_start": round(ts, 3),
                        "t_end": round(te, 3),
                        "params": {
                            "text": txt,
                            "x": cx,
                            "y": cy,
                            "font_family": "Inter",
                            "font_size": _font_size_from_rule(txt, None),
                            "font_weight": "800",
                            "color": "#FFFFFF",
                            "highlight_color": "#FFD84D",
                            "stroke_color": "#000000",
                            "stroke_width": 3,
                            "caption_animation": "word_reveal",
                            "caption_mode": "line_simple",
                            "background_color": "#000000",
                            "background_opacity": 0.45,
                        },
                    }
                )

    seen: set[tuple[Any, float, float, str]] = set()
    out: list[dict[str, Any]] = []
    for c in sorted(raw, key=lambda x: (x["t_start"], x["t_end"], str(x.get("index")))):
        k = (c.get("index"), c["t_start"], c["t_end"], c["params"].get("text", ""))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def _write_debug_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _collect_screen_bg_parse_warnings(seg_files: list[Path]) -> list[str]:
    warnings: list[str] = []
    for p in seg_files:
        obj = _parse_refiner_segment_with_fallback(p, debug_dir=p.parent.parent / "debug")
        if not isinstance(obj, dict):
            warnings.append(f"screen_bg_skipped_unparseable_segment:{p.name}")
            continue
        sb = obj.get("screen_bg_timeline")
        if sb is None:
            continue
        if not isinstance(sb, list):
            warnings.append(f"screen_bg_timeline_not_list:{p.name}")
            continue
        for i, row in enumerate(sb):
            if not isinstance(row, dict):
                warnings.append(f"screen_bg_timeline_item_not_object:{p.name}:{i}")
    return warnings


def _verify_inter_or_raise(inter: dict[str, Any], *, has_audio: bool, has_captions: bool) -> None:
    video = inter.get("video")
    if not isinstance(video, dict):
        raise ValueError("inter.video missing")
    size = video.get("size")
    if not isinstance(size, dict) or "width" not in size or "height" not in size:
        raise ValueError("inter.video.size invalid")
    if "fps" not in video:
        raise ValueError("inter.video.fps missing")
    if "output_path" not in video:
        raise ValueError("inter.video.output_path missing")
    elements = inter.get("elements")
    if not isinstance(elements, list):
        raise ValueError("inter.elements missing")
    if has_audio and not any(str(e.get("type", "")).lower() in {"music", "audio"} for e in elements if isinstance(e, dict)):
        raise ValueError("audio exists but inter has no audio element")
    if has_captions and not any(str(e.get("element_id", "")) == "caption_track_1" for e in elements if isinstance(e, dict)):
        raise ValueError("captions exist but caption_track_1 missing in inter")


def _normalize_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    for c in cues:
        try:
            ts = round(float(c.get("t_start", c.get("start", 0.0)) or 0.0), 3)
            te = round(float(c.get("t_end", c.get("end", ts)) or ts), 3)
        except Exception:
            continue
        text = str(c.get("text", "")).strip()
        if not text or te <= ts:
            continue
        key = (text, ts, te)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "t_start": ts, "t_end": te})
    out.sort(key=lambda x: x["t_start"])
    return out


def _normalize_caption_jobs(caption_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize captions exactly from refiner cues, but dedupe correctly.

    Priority:
    - Use cue index if available.
    - Otherwise dedupe by (text, t_start, t_end).
    - Never allow duplicate overlapping caption text.
    """
    raw: list[dict[str, Any]] = []

    for row in caption_jobs:
        cue = row.get("cue") if isinstance(row.get("cue"), dict) else {}
        track = row.get("track") if isinstance(row.get("track"), dict) else {}

        try:
            ts = round(float(cue.get("t_start", cue.get("start", 0.0)) or 0.0), 3)
            te = round(float(cue.get("t_end", cue.get("end", ts)) or ts), 3)
        except Exception:
            continue

        text = str(cue.get("text", "")).strip()
        if not text or te <= ts:
            continue

        layout = track.get("layout") if isinstance(track.get("layout"), dict) else {}
        style = track.get("style") if isinstance(track.get("style"), dict) else {}
        anim = track.get("animation") if isinstance(track.get("animation"), dict) else {}

        lx = _to_float(layout.get("x"), 90.0)
        ly = _to_float(cue.get("y", layout.get("y")), 1450.0)
        lw = _to_float(layout.get("width"), 900.0)
        lh = _to_float(layout.get("height"), 300.0)

        cx = lx + lw / 2.0
        cy = ly + lh / 2.0

        bg = style.get("background_color")
        highlight_words = cue.get("highlight_words") if isinstance(cue.get("highlight_words"), list) else None

        font_size = style.get("font_size")
        if font_size is None:
            font_size = _font_size_from_rule(text, style.get("font_size_rule"))

        raw.append(
            {
                "index": cue.get("index"),
                "text": text,
                "t_start": ts,
                "t_end": te,
                "params": _drop_nones(
                    {
                        "text": text,
                        "x": round(cx, 3),
                        "y": round(cy, 3),
                        "font_family": style.get("font_family", "Inter"),
                        "font_size": _extract_font_size(style, text),
                        "font_weight": style.get("font_weight", "800"),
                        "color": style.get("text_color", "#FFFFFF"),
                        "highlight_color": style.get("highlight_color", "#FFD84D"),
                        "stroke_color": "#000000",
                        "stroke_width": 3,
                        "caption_animation": anim.get("type", "word_reveal"),
                        "caption_mode": "word_reveal_v2",
                        "background_opacity": _rgba_opacity(bg),
                        "background_color": _rgba_color(bg),
                        "important_words": highlight_words,
                    }
                ),
            }
        )

    # Deduplicate.
    best: dict[Any, dict[str, Any]] = {}
    for item in raw:
        if item["index"] is not None:
            key = ("idx", int(item["index"]))
        else:
            key = ("txt", item["text"], item["t_start"], item["t_end"])

        old = best.get(key)
        if old is None:
            best[key] = item
        else:
            # Prefer cleaner/shorter correct duration if duplicates exist.
            old_d = old["t_end"] - old["t_start"]
            new_d = item["t_end"] - item["t_start"]
            if new_d < old_d:
                best[key] = item

    out = list(best.values())
    out.sort(key=lambda x: (x["t_start"], x["t_end"], str(x.get("index"))))
    return [{"t_start": x["t_start"], "t_end": x["t_end"], "params": x["params"]} for x in out]

def _font_size_from_rule(text: str, rule: Any) -> int:
    words = [w for w in str(text).split() if w.strip()]
    n = len(words)
    if n <= 3:
        return 70
    if n <= 7:
        return 62
    return 56

def _pick_first_audio_id(by_id: dict[str, dict[str, Any]]) -> str | None:
    for eid, row in by_id.items():
        if _normalize_media_type(str(row.get("media_type", ""))) in {"audio", "music", "sfx"}:
            return eid
    return None


def _normalize_media_type(media_type: str) -> str:
    mt = str(media_type or "").strip().lower()
    if mt in {"audio", "music", "sfx", "image", "video", "gif", "sticker"}:
        return mt
    if "no audio video" in mt:
        return "video"
    if "video" in mt:
        return "video"
    if "gif" in mt:
        return "gif"
    if "sticker" in mt:
        return "sticker"
    if "image" in mt:
        return "image"
    if "audio" in mt:
        return "audio"
    return mt


def _collect_visual_intervals(elements: list[dict[str, Any]]) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for e in elements:
        if not isinstance(e, dict):
            continue
        if str(e.get("type", "")).lower() not in {"video", "image", "gif"}:
            continue
        actions = e.get("actions")
        if not isinstance(actions, list):
            continue
        for a in actions:
            if not isinstance(a, dict):
                continue
            try:
                ts = float(a.get("t_start", 0.0) or 0.0)
                te = float(a.get("t_end", ts) or ts)
            except Exception:
                continue
            if te > ts:
                intervals.append((ts, te))
    intervals.sort(key=lambda x: (x[0], x[1]))
    return intervals


def _has_visual_in_window(intervals: list[tuple[float, float]], ts: float, te: float) -> bool:
    for a, b in intervals:
        if a < te and ts < b:
            return True
    return False


def _grouped_caption_lookup(media_json: dict[str, Any]) -> dict[int, tuple[float, float, str]]:
    out: dict[int, tuple[float, float, str]] = {}
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return out
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        groups = transcript.get("caption_groups")
        if not isinstance(groups, list):
            continue
        for i, row in enumerate(groups):
            if not isinstance(row, dict):
                continue
            try:
                s = float(row.get("start"))
                e = float(row.get("end"))
            except Exception:
                continue
            txt = str(row.get("text", "")).strip()
            out[i] = (round(s, 3), round(e, 3), txt)
        if out:
            return out
    return out


def _repair_caption_cues_from_grouped_map(
    cues: list[dict[str, Any]],
    grouped_lookup: dict[int, tuple[float, float, str]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cue in cues:
        c = dict(cue)
        idx = c.get("index")
        ts = float(c.get("t_start", 0.0))
        te = float(c.get("t_end", ts))
        if isinstance(idx, int) and idx in grouped_lookup and te <= ts:
            gs, ge, gt = grouped_lookup[idx]
            c["t_start"] = gs
            c["t_end"] = ge
            params = c.get("params") if isinstance(c.get("params"), dict) else {}
            if isinstance(params, dict) and gt:
                params["text"] = gt
                c["params"] = params
        out.append(c)
    out.sort(key=lambda x: (float(x.get("t_start", 0.0)), float(x.get("t_end", 0.0))))
    return out


def _looped_action_windows(ts: float, te: float, src_duration: float) -> list[tuple[float, float, float, float]]:
    seg_dur = max(0.0, te - ts)
    if seg_dur <= 0.0:
        return []
    if src_duration <= 0.05:
        return [(round(ts, 3), round(te, 3), 0.0, round(seg_dur, 3))]
    out: list[tuple[float, float, float, float]] = []
    cur = ts
    while cur < te - 1e-6:
        chunk = min(src_duration, te - cur)
        ws = round(cur, 3)
        we = round(cur + chunk, 3)
        out.append((ws, we, 0.0, round(chunk, 3)))
        cur += chunk
    return out


def _clip_elements_to_duration(elements: list[dict[str, Any]], target_duration: float) -> None:
    for e in elements:
        if not isinstance(e, dict):
            continue
        actions = e.get("actions")
        if not isinstance(actions, list):
            continue
        clipped: list[dict[str, Any]] = []
        for a in actions:
            if not isinstance(a, dict):
                continue
            try:
                ts = float(a.get("t_start", 0.0) or 0.0)
                te = float(a.get("t_end", ts) or ts)
            except Exception:
                continue
            ts = max(0.0, min(ts, target_duration))
            te = max(0.0, min(te, target_duration))
            if te <= ts:
                continue
            na = dict(a)
            na["t_start"] = round(ts, 3)
            na["t_end"] = round(te, 3)
            clipped.append(na)
        clipped.sort(key=lambda x: (x.get("t_start", 0.0), x.get("t_end", 0.0)))
        e["actions"] = clipped
        if clipped:
            start = float(clipped[0]["t_start"])
            end = float(clipped[-1]["t_end"])
            timing = e.get("timing") if isinstance(e.get("timing"), dict) else {}
            timing["start"] = round(start, 3)
            timing["duration"] = round(max(0.0, end - start), 3)
            e["timing"] = timing


def _probe_duration(row: Any) -> float:
    if not isinstance(row, dict):
        return 0.0
    try:
        d = float(row.get("duration") or 0.0)
        return round(d, 3)
    except Exception:
        return 0.0


def _probe_duration_from_path(path_like: Any) -> float:
    p = str(path_like or "").strip()
    if not p:
        return 0.0
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                p,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return 0.0
        val = float((proc.stdout or "").strip())
        return round(max(0.0, val), 3)
    except Exception:
        return 0.0




def _load_word_map_all(path_override: str | Path | None = None) -> list[dict[str, Any]]:
    p = Path(path_override) if path_override else Path("output/word_timing_maps/word_timing_map_all.json")
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    # Prefer media_1 (main audio), else flatten.
    if isinstance(data, dict):
        if isinstance(data.get("media_1"), list):
            return [x for x in data.get("media_1", []) if isinstance(x, dict)]
        out: list[dict[str, Any]] = []
        for v in data.values():
            if isinstance(v, list):
                out.extend([x for x in v if isinstance(x, dict)])
        return out
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _norm_word(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _build_word_sequence_for_cue(
    cue_text: str,
    cue_start: float,
    cue_end: float,
    word_map_all: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tokens = [t for t in str(cue_text).split(" ") if t.strip()]
    if not tokens or not word_map_all:
        return []
    norm_tokens = [_norm_word(t) for t in tokens]
    candidates: list[dict[str, Any]] = []
    for w in word_map_all:
        try:
            ws = float(w.get("start"))
            we = float(w.get("end"))
        except Exception:
            continue
        if we <= cue_start or ws >= cue_end:
            continue
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        candidates.append({"text": text, "start": ws, "end": we, "norm": _norm_word(text)})
    if not candidates:
        return []
    candidates.sort(key=lambda x: x["start"])
    seq: list[dict[str, Any]] = []
    ci = 0
    for nt in norm_tokens:
        found = None
        for j in range(ci, len(candidates)):
            if candidates[j]["norm"] == nt:
                found = candidates[j]
                ci = j + 1
                break
        if found is None:
            continue
        seq.append(
            {
                "text": found["text"],
                "start": round(max(cue_start, found["start"]), 3),
                "end": round(min(cue_end, found["end"]), 3),
            }
        )
    return [x for x in seq if x["end"] > x["start"]]


def _collect_screen_bg_events(seg_files: list[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for p in seg_files:
        obj = _parse_refiner_segment_with_fallback(p, debug_dir=p.parent.parent / "debug")
        if not isinstance(obj, dict):
            continue
        timeline = obj.get("screen_bg_timeline")
        if not isinstance(timeline, list):
            continue
        for ev in timeline:
            if not isinstance(ev, dict):
                continue
            try:
                ts = float(ev.get("t_start", 0.0) or 0.0)
                te = float(ev.get("t_end", ts) or ts)
            except Exception:
                continue
            if te <= ts:
                continue
            color = str(ev.get("color", "#000000")).strip() or "#000000"
            try:
                opacity = float(ev.get("opacity", 0.25) or 0.25)
            except Exception:
                opacity = 0.25
            events.append(
                {
                    "type": "tint",
                    "t_start": round(ts, 3),
                    "t_end": round(te, 3),
                    "color": color,
                    "opacity": max(0.0, min(1.0, opacity)),
                }
            )
    events.sort(key=lambda x: x["t_start"])
    return events


def _probe_size(row: Any) -> tuple[int, int]:
    if not isinstance(row, dict):
        return 1920, 1080
    try:
        w = int(float(row.get("width") or 1920))
        h = int(float(row.get("height") or 1080))
        if w <= 0 or h <= 0:
            return 1920, 1080
        return w, h
    except Exception:
        return 1920, 1080


def _compute_scale(*, src_w: int, src_h: int, target_w: float, target_h: float, fit: str) -> float:
    if src_w <= 0 or src_h <= 0 or target_w <= 0 or target_h <= 0:
        return 1.0
    sx = float(target_w) / float(src_w)
    sy = float(target_h) / float(src_h)
    if fit == "contain":
        s = min(sx, sy)
    else:
        s = max(sx, sy)
    return max(0.01, s)


def _to_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _transition_to_fade_seconds(tr: dict[str, Any]) -> float | None:
    if not isinstance(tr, dict):
        return None
    t = str(tr.get("type") or "").strip().lower()
    if t != "fade":
        return None
    try:
        d = float(tr.get("duration") or 0.15)
        return max(0.0, d)
    except Exception:
        return 0.15


def _drop_nones(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _extract_font_size(style: dict[str, Any], text: str | None = None) -> int | None:
    raw = style.get("font_size")
    if raw is not None:
        try:
            return int(float(raw))
        except Exception:
            pass

    if text:
        return _font_size_from_rule(text, style.get("font_size_rule"))

    return 64


def _rgba_opacity(color: Any) -> float | None:
    if not isinstance(color, str):
        return None
    m = re.match(r"rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*([0-9]*\.?[0-9]+)\s*\)", color.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return max(0.0, min(1.0, float(m.group(1))))
    except Exception:
        return None


def _rgba_color(color: Any) -> str | None:
    if not isinstance(color, str):
        return None
    m = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9]*\.?[0-9]+)\s*\)", color.strip(), flags=re.IGNORECASE)
    if not m:
        return color
    r, g, b = [max(0, min(255, int(x))) for x in (m.group(1), m.group(2), m.group(3))]
    return f"#{r:02X}{g:02X}{b:02X}"


def _collect_screen_tint_events(seg_files: list[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for p in seg_files:
        obj = _load_segment_json_from_text(p)
        if not isinstance(obj, dict):
            continue
        cap = obj.get("caption_plan") or obj.get("caption_track") or {}
        if not isinstance(cap, dict):
            continue
        cues = cap.get("cues")
        if not isinstance(cues, list):
            continue
        for cue in cues:
            if not isinstance(cue, dict):
                continue
            so = cue.get("style_override")
            if not isinstance(so, dict):
                continue
            bg = so.get("background_color")
            hex_color = _rgba_color(bg)
            if not isinstance(hex_color, str):
                continue
            try:
                ts = float(cue.get("t_start", cue.get("start", 0.0)) or 0.0)
                te = float(cue.get("t_end", cue.get("end", ts)) or ts)
            except Exception:
                continue
            if te <= ts:
                continue
            events.append(
                {
                    "type": "tint",
                    "t_start": round(ts, 3),
                    "t_end": round(te, 3),
                    "color": hex_color,
                    "opacity": 0.28,
                }
            )
    return events


def _simplify_inter_for_low_memory(inter: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(inter))
    elements = out.get("elements")
    if not isinstance(elements, list):
        return out
    for e in elements:
        if not isinstance(e, dict):
            continue
        if str(e.get("type", "")).lower() != "caption":
            continue
        actions = e.get("actions")
        if not isinstance(actions, list):
            continue
        for a in actions:
            if not isinstance(a, dict):
                continue
            params = a.get("params")
            if not isinstance(params, dict):
                continue
            params.pop("word_timing_sequence", None)
            params["caption_mode"] = "line_simple"
            params["caption_animation"] = "fade"
    return out




def main() -> None:
    parser = argparse.ArgumentParser(description="Merge refiner segment outputs and render one video.")
    parser.add_argument("--segment-outputs-dir", default="output/refiner_segment_outputs")
    parser.add_argument("--media-json", default="output/media.json")
    parser.add_argument("--word-map-all", default=None, help="Optional path to word_timing_map_all.json")
    parser.add_argument("--output-inter", default="output/inter_from_segment_outputs.json")
    parser.add_argument("--output-video", default="output/a2v_video_from_segment_outputs.mp4")
    args = parser.parse_args()

    inter_path, video_path = render_segment_outputs_to_video(
        segment_outputs_dir=args.segment_outputs_dir,
        media_json_path=args.media_json,
        word_map_all_path=args.word_map_all,
        output_inter_path=args.output_inter,
        output_video_path=args.output_video,
    )
    print(json.dumps({"inter": str(inter_path), "video": str(video_path)}, indent=2))


if __name__ == "__main__":
    main()
