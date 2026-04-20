from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from vasp.a2v.v2.creativity_policy import (
    CREATIVITY_LEVELS,
    allowed_animation,
    allowed_transition,
    clamp_visual_layout,
    get_creativity_policy,
    normalize_caption_layout,
    normalize_caption_style,
)
from vasp.a2v.v2.refiner_presets_v3 import resolve_refiner_preset_bundle
from vasp.a2v.v2.renderer_v2 import render_inter_v2


DEFAULT_VISUAL_LAYOUT = {
    "x": 0,
    "y": 544,
    "width": 1080,
    "height": 800,
    "z_index": 3,
    "opacity": 1.0,
    "fit": "contain",
    "caption_safe": True,
}


def _read_json_from_txt(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if m:
        try:
            obj = json.loads(m.group(1).strip())
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    extracted = _extract_balanced_json(text)
    if extracted is None:
        return None
    try:
        obj = json.loads(extracted)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_balanced_json(text: str) -> str | None:
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


def _to_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _extract_caption_groups(media_json: dict[str, Any]) -> list[dict[str, Any]]:
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
        for i, g in enumerate(groups):
            if not isinstance(g, dict):
                continue
            s = _to_float(g.get("start"), -1.0)
            e = _to_float(g.get("end"), -1.0)
            txt = str(g.get("text", "")).strip()
            if s < 0 or e <= s or not txt:
                continue
            out.append({"index": i, "text": txt, "start": round(s, 3), "end": round(e, 3)})
        return out
    return []


def _build_media_registry(media_json: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str | None, float]:
    inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    registry: dict[str, dict[str, Any]] = {}
    main_audio_id = None
    audio_duration = 0.0

    for row in inputs:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id", "")).strip()
        if not eid:
            continue
        p = probe.get(eid, {}) if isinstance(probe, dict) else {}
        media_type = str(row.get("media_type", "")).strip().lower()
        src = str(row.get("path", "")).strip()
        entry = {
            "element_id": eid,
            "type": media_type,
            "source_uri": src,
            "duration": _to_float(p.get("duration"), 0.0),
            "width": p.get("width"),
            "height": p.get("height"),
            "fps": p.get("fps"),
        }
        registry[eid] = entry
        if main_audio_id is None and ("audio" in media_type or media_type in {"music", "sfx"}):
            main_audio_id = eid
            audio_duration = max(audio_duration, _to_float(p.get("duration"), 0.0))
    return registry, main_audio_id, round(audio_duration, 3)


def _safe_style_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    safe_keys = {
        "font_family",
        "font_size",
        "font_weight",
        "text_color",
        "highlight_color",
        "stroke_color",
        "stroke_width",
        "background_color",
        "align",
        "vertical_align",
    }
    out = dict(base)
    for k, v in overlay.items():
        if k in safe_keys and v is not None:
            out[k] = v
    out["font_size"] = max(40, int(_to_float(out.get("font_size"), 64)))
    return out


def _normalize_visual_timeline(rows: list[dict[str, Any]], duration: float, warnings: list[str]) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for r in rows:
        ts = max(0.0, min(duration, _to_float(r.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _to_float(r.get("t_end"), ts)))
        if te <= ts:
            warnings.append(f"drop_invalid_visual:{r.get('element_id')}:{ts}-{te}")
            continue
        key = (
            r.get("element_id"),
            r.get("source_ref"),
            round(ts, 3),
            round(te, 3),
        )
        if key in seen:
            continue
        seen.add(key)
        n = dict(r)
        n["t_start"] = round(ts, 3)
        n["t_end"] = round(te, 3)
        valid.append(n)

    valid.sort(key=lambda x: (x["t_start"], x["t_end"]))
    out: list[dict[str, Any]] = []
    for item in valid:
        if not out:
            out.append(item)
            continue
        prev = out[-1]
        if item["t_start"] < prev["t_end"]:
            prev["t_end"] = round(item["t_start"], 3)
            if prev["t_end"] <= prev["t_start"]:
                dropped = out.pop()
                warnings.append(f"drop_overlap_zero_duration:{dropped.get('element_id')}")
        out.append(item)
    return [x for x in out if x["t_end"] > x["t_start"]]


def _cue_overlaps_visual(cue: dict[str, Any], visuals: list[dict[str, Any]]) -> bool:
    cs = _to_float(cue.get("t_start"), 0.0)
    ce = _to_float(cue.get("t_end"), cs)
    for v in visuals:
        if _to_float(v.get("t_start"), 0.0) < ce and cs < _to_float(v.get("t_end"), 0.0):
            return True
    return False


def _extract_visual_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    # Support both formats:
    # 1) flat row {element_id, source_ref, t_start, t_end, ...}
    # 2) nested row {"visual": {..., time_hint:{start,end}}}
    row = raw
    if isinstance(raw.get("visual"), dict):
        row = raw["visual"]
    if not isinstance(row, dict):
        return None

    eid = str(
        row.get("source_ref")
        or row.get("element_id")
        or row.get("visual_id")
        or raw.get("source_ref")
        or raw.get("element_id")
        or raw.get("visual_id")
        or ""
    ).strip()

    ts = row.get("t_start")
    te = row.get("t_end")
    if ts is None:
        ts = row.get("start")
    if te is None:
        te = row.get("end")
    if (ts is None or te is None) and isinstance(row.get("time_hint"), dict):
        hint = row["time_hint"]
        ts = hint.get("start")
        te = hint.get("end")
    if (ts is None or te is None) and isinstance(raw.get("time_hint"), dict):
        hint = raw["time_hint"]
        ts = hint.get("start")
        te = hint.get("end")

    if ts is None or te is None:
        return None

    return {
        "element_id": eid,
        "source_ref": eid,
        "type": row.get("type"),
        "role": row.get("role"),
        "t_start": _to_float(ts, 0.0),
        "t_end": _to_float(te, 0.0),
        "transition_in": row.get("transition_in"),
        "transition_out": row.get("transition_out"),
        "animation": row.get("animation"),
        "layout": row.get("layout") if isinstance(row.get("layout"), dict) else None,
    }


def _merge_preset(base: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    out.update({k: v for k, v in raw.items() if v is not None})
    return out


def _segment_preset_bundle(seg: dict[str, Any]) -> dict[str, Any]:
    return {
        "preset_bundle": seg.get("preset_bundle"),
        "background_preset": seg.get("background_preset"),
        "caption_preset": seg.get("caption_preset"),
        "caption_layout_preset": seg.get("caption_layout_preset"),
        "visual_layout_preset": seg.get("visual_layout_preset"),
        "caption_animation_preset": seg.get("caption_animation_preset"),
        "visual_animation_preset": seg.get("visual_animation_preset"),
        "transition_preset": seg.get("transition_preset"),
    }


def validate_inter_v2(inter: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    video = inter.get("video")
    if not isinstance(video, dict):
        errs.append("video missing")
        return errs
    w = _to_float(video.get("width"), 0)
    h = _to_float(video.get("height"), 0)
    d = _to_float(video.get("duration"), 0)
    if w <= 0 or h <= 0:
        errs.append("video size invalid")
    if d <= 0:
        errs.append("video duration invalid")
    visuals = inter.get("visual_timeline", [])
    if isinstance(visuals, list):
        prev_end = -1.0
        for v in sorted(visuals, key=lambda x: _to_float(x.get("t_start"), 0.0)):
            ts = _to_float(v.get("t_start"), 0.0)
            te = _to_float(v.get("t_end"), ts)
            if te <= ts:
                errs.append(f"invalid visual duration:{v.get('element_id')}")
            if ts < prev_end:
                errs.append("overlapping visuals found")
            prev_end = max(prev_end, te)
            lay = v.get("layout", {})
            if isinstance(lay, dict):
                x = _to_float(lay.get("x"), 0.0)
                y = _to_float(lay.get("y"), 0.0)
                lw = _to_float(lay.get("width"), 0.0)
                lh = _to_float(lay.get("height"), 0.0)
                if x < 0 or y < 0 or x + lw > w or y + lh > h:
                    errs.append(f"visual outside screen:{v.get('element_id')}")
    caps = (((inter.get("caption_track") or {}).get("cues")) or [])
    if isinstance(caps, list):
        for c in caps:
            cs = _to_float(c.get("t_start"), 0.0)
            ce = _to_float(c.get("t_end"), cs)
            if ce <= cs or ce > d + 1e-3:
                errs.append("caption timing invalid")
    a = inter.get("audio_track") or {}
    if not isinstance(a, dict) or not str(a.get("source_uri", "")).strip():
        errs.append("audio source missing")
    return errs


def build_inter_v2(
    *,
    segment_outputs_dir: str | Path,
    media_json_path: str | Path,
    output_inter_path: str | Path,
    output_video_path: str | Path,
    creativity_level: int = 2,
) -> dict[str, Any]:
    policy = get_creativity_policy(creativity_level)
    sdir = Path(segment_outputs_dir)
    media_path = Path(media_json_path)
    inter_path = Path(output_inter_path)
    warnings: list[str] = []

    media_json = json.loads(media_path.read_text(encoding="utf-8"))
    registry, main_audio_id, audio_duration = _build_media_registry(media_json)
    if main_audio_id is None:
        raise ValueError("No audio element found in media.json")

    # V2 source of truth: refiner_output_segment_*.txt
    segment_files = sorted(sdir.glob("refiner_output_segment_*.txt"))
    if not segment_files:
        # Backward-compatible fallback only.
        segment_files = sorted(sdir.glob("refiner_segment_output_*.txt"))
    if not segment_files:
        raise FileNotFoundError(
            f"No refiner segment output files found in {sdir}. "
            "Expected refiner_output_segment_*.txt (v2) or refiner_segment_output_*.txt (legacy)."
        )
    parsed_segments: list[dict[str, Any]] = []
    for f in segment_files:
        obj = _read_json_from_txt(f)
        if not isinstance(obj, dict):
            warnings.append(f"skip_unparseable_segment:{f.name}")
            continue
        parsed_segments.append(obj)

    visual_rows: list[dict[str, Any]] = []
    background_rows: list[dict[str, Any]] = []
    style_overlay: dict[str, Any] = {}
    anim_overlay: dict[str, Any] = {}
    visual_preset_by_key: dict[tuple[str, float, float], dict[str, Any]] = {}

    for seg in parsed_segments:
        preset_bundle = resolve_refiner_preset_bundle(_segment_preset_bundle(seg))
        bg_default = preset_bundle.get("background") or {}
        if bg_default:
            ts = _to_float(seg.get("t_start"), 0.0)
            te = _to_float(seg.get("t_end"), ts)
            if te > ts:
                bg = dict(bg_default)
                bg.update({"t_start": ts, "t_end": te})
                background_rows.append(bg)
        tl = seg.get("visual_timeline")
        if not isinstance(tl, list):
            tl = seg.get("final_timeline")
        if not isinstance(tl, list):
            warnings.append("segment_missing_visual_timeline")
            continue
        for raw in tl:
            if not isinstance(raw, dict):
                continue
            v = _extract_visual_row(raw)
            if not isinstance(v, dict):
                warnings.append("skip_unusable_visual_row")
                continue
            eid = str(v.get("source_ref") or v.get("element_id") or "").strip()
            if not eid or eid not in registry:
                warnings.append(f"skip_missing_media_ref:{eid}")
                continue
            reg_type = str(registry[eid].get("type") or "").strip().lower()
            vtype = str(v.get("type") or reg_type or "image").strip().lower()
            if "audio" in vtype or "audio" in reg_type:
                warnings.append(f"skip_audio_in_visual_timeline:{eid}")
                continue
            vt = {
                "element_id": eid,
                "source_ref": eid,
                "type": str(v.get("type") or registry[eid].get("type") or "image"),
                "role": str(v.get("role") or "supporting_visual"),
                "source_uri": registry[eid].get("source_uri"),
                "t_start": _to_float(v.get("t_start"), 0.0),
                "t_end": _to_float(v.get("t_end"), 0.0),
                "layout": clamp_visual_layout(
                    _merge_preset(preset_bundle.get("visual_layout") or DEFAULT_VISUAL_LAYOUT, v.get("layout") if isinstance(v.get("layout"), dict) else {}),
                    creativity_level,
                    warnings,
                ),
                "transition_in": allowed_transition(
                    _merge_preset(preset_bundle.get("transition") or {}, v.get("transition_in") if isinstance(v.get("transition_in"), dict) else {}),
                    creativity_level,
                ),
                "transition_out": allowed_transition(
                    _merge_preset(preset_bundle.get("transition") or {}, v.get("transition_out") if isinstance(v.get("transition_out"), dict) else {}),
                    creativity_level,
                ),
                "animation": allowed_animation(
                    _merge_preset(preset_bundle.get("visual_animation") or {"type": "none"}, v.get("animation") if isinstance(v.get("animation"), dict) else {}),
                    creativity_level,
                ),
            }
            vt["layout"]["opacity"] = max(1.0, _to_float((vt.get("layout") or {}).get("opacity"), 1.0))
            visual_rows.append(vt)
            visual_preset_by_key[(eid, round(vt["t_start"], 3), round(vt["t_end"], 3))] = preset_bundle
        cap_policy = seg.get("caption_render_policy") if isinstance(seg.get("caption_render_policy"), dict) else {}
        cap_track = seg.get("caption_track") if isinstance(seg.get("caption_track"), dict) else {}
        if isinstance(cap_policy.get("style"), dict):
            style_overlay.update(cap_policy.get("style"))
        elif isinstance(cap_track.get("style"), dict):
            style_overlay.update(cap_track.get("style"))
        elif preset_bundle.get("caption_style"):
            style_overlay.update(preset_bundle["caption_style"])
        if isinstance(cap_policy.get("animation"), dict):
            anim_overlay.update(cap_policy.get("animation"))
        elif isinstance(cap_track.get("animation"), dict):
            anim_overlay.update(cap_track.get("animation"))
        elif preset_bundle.get("caption_animation"):
            anim_overlay.update(preset_bundle["caption_animation"])

    groups = _extract_caption_groups(media_json)
    max_caption_end = max((_to_float(g.get("end"), 0.0) for g in groups), default=0.0)
    max_visual_end = max((_to_float(v.get("t_end"), 0.0) for v in visual_rows), default=0.0)
    duration = audio_duration if audio_duration > 0 else round(max(max_caption_end, max_visual_end), 3)
    if duration <= 0:
        raise ValueError("Could not resolve non-zero video duration")

    visuals = _normalize_visual_timeline(visual_rows, duration, warnings)

    caption_style = normalize_caption_style(_safe_style_merge(
        {
            "font_family": "Inter",
            "font_size": 64,
            "font_weight": "800",
            "text_color": "#FFFFFF",
            "highlight_color": "#FFD84D",
            "stroke_color": "#000000",
            "stroke_width": 3,
            "background_color": "rgba(0,0,0,0.45)",
            "align": "center",
            "vertical_align": "middle",
        },
        style_overlay,
    ), creativity_level, warnings)
    caption_animation = allowed_animation((
        {"type": str(anim_overlay.get("type", "word_reveal")), "intensity": str(anim_overlay.get("intensity", "medium"))}
        if anim_overlay
        else {"type": "word_reveal", "intensity": "medium"}
    ), creativity_level)

    cues: list[dict[str, Any]] = []
    for g in groups:
        s = max(0.0, min(duration, _to_float(g.get("start"), 0.0)))
        e = max(0.0, min(duration, _to_float(g.get("end"), s)))
        if e <= s:
            warnings.append(f"skip_bad_caption_group:{g.get('index')}")
            continue
        has_visual = _cue_overlaps_visual({"t_start": s, "t_end": e}, visuals)
        layout = normalize_caption_layout((
            {"x": 90, "y": 1450, "width": 900, "height": 300}
            if has_visual
            else {"x": 120, "y": 820, "width": 840, "height": 300}
        ), creativity_level, has_visual, warnings)
        cues.append(
            {
                "index": g.get("index"),
                "text": g.get("text"),
                "t_start": round(s, 3),
                "t_end": round(e, 3),
                "layout": layout,
            }
        )

    by_visual_eid: dict[str, dict[str, Any]] = {}
    for v in visuals:
        eid = str(v.get("element_id"))
        if eid not in by_visual_eid:
            by_visual_eid[eid] = {
                "element_id": eid,
                "type": v.get("type"),
                "source_uri": v.get("source_uri"),
                "actions": [],
            }
        by_visual_eid[eid]["actions"].append(
            {
                "t_start": v["t_start"],
                "t_end": v["t_end"],
                "op": "show",
                "params": {
                    "element_id": eid,
                    "source_uri": v.get("source_uri"),
                    "layout": v.get("layout") or dict(DEFAULT_VISUAL_LAYOUT),
                    "transition_in": v.get("transition_in", {"type": "cut", "duration": 0.0}),
                    "transition_out": v.get("transition_out", {"type": "cut", "duration": 0.0}),
                    "animation": v.get("animation", {"type": "none", "intensity": "low"}),
                },
            }
        )
    visual_actions = list(by_visual_eid.values())
    caption_actions = [
        {
            "t_start": c["t_start"],
            "t_end": c["t_end"],
            "op": "show",
            "params": {"text": c["text"], "layout": c["layout"]},
        }
        for c in cues
    ]

    main_audio = registry[main_audio_id]
    inter = {
        "version": "2.0",
        "video": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "duration": round(duration, 3),
            "bg_color": "#000000",
            "output_path": str(output_video_path).replace("\\", "/"),
        },
        "media_registry": registry,
        "visual_timeline": visuals,
        "background_timeline": background_rows,
        "caption_track": {
            "element_id": "caption_track_1",
            "style": caption_style,
            "animation": caption_animation,
            "cues": cues,
            "actions": caption_actions,
        },
        "audio_track": {
            "element_id": main_audio_id,
            "source_uri": main_audio.get("source_uri"),
            "t_start": 0.0,
            "t_end": round(duration, 3),
            "volume": 1.0,
        },
        "elements": visual_actions
        + [
            {
                "element_id": "caption_track_1",
                "type": "caption",
                "actions": caption_actions,
            },
            {
                "element_id": main_audio_id,
                "type": "audio",
                "source_uri": main_audio.get("source_uri"),
                "actions": [{"t_start": 0.0, "t_end": round(duration, 3), "op": "play", "params": {"volume": 1.0}}],
            },
        ],
        "warnings": warnings,
        "creativity_level": creativity_level,
        "style_policy": {k: v for k, v in policy.items() if k != "rules_text"},
    }

    errs = validate_inter_v2(inter)
    if errs:
        raise ValueError("inter_v2 validation failed: " + "; ".join(errs))

    inter_path.parent.mkdir(parents=True, exist_ok=True)
    inter_path.write_text(json.dumps(inter, ensure_ascii=False, indent=2), encoding="utf-8")
    return inter


def main() -> None:
    parser = argparse.ArgumentParser(description="Build A2V inter_v2.json from refiner segment outputs.")
    parser.add_argument("--segment-outputs-dir", required=True)
    parser.add_argument("--media-json", required=True)
    parser.add_argument("--output-inter", required=True)
    parser.add_argument("--output-video", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--creativity", type=int, default=2, choices=CREATIVITY_LEVELS)
    args = parser.parse_args()

    inter = build_inter_v2(
        segment_outputs_dir=args.segment_outputs_dir,
        media_json_path=args.media_json,
        output_inter_path=args.output_inter,
        output_video_path=args.output_video,
        creativity_level=args.creativity,
    )
    print(
        "[A2V_V2][COMBINER] built inter_v2: "
        f"visuals={len(inter.get('visual_timeline', []))}, "
        f"captions={len(((inter.get('caption_track') or {}).get('cues') or []))}, "
        f"warnings={len(inter.get('warnings', []))}"
    )
    if args.render:
        render_inter_v2(args.output_inter)


if __name__ == "__main__":
    main()
