from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from vasp.render.element_renderer import render_from_json


def render_segment_outputs_to_video(
    *,
    segment_outputs_dir: str | Path,
    media_json_path: str | Path,
    word_map_all_path: str | Path | None = None,
    output_inter_path: str | Path = "output/inter_from_segment_outputs.json",
    output_video_path: str | Path = "output/a2v_video_from_segment_outputs.mp4",
) -> tuple[Path, Path]:
    """Merge per-segment refiner outputs into one inter.json and render it."""
    sdir = Path(segment_outputs_dir)
    media_path = Path(media_json_path)
    inter_path = Path(output_inter_path)
    video_path = Path(output_video_path)

    if not sdir.exists():
        raise FileNotFoundError(f"segment outputs dir not found: {sdir}")
    if not media_path.exists():
        raise FileNotFoundError(f"media json not found: {media_path}")

    media_json = json.loads(media_path.read_text(encoding="utf-8"))
    media_inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    probe = ((media_json.get("media_context") or {}).get("probe") or {})

    by_id: dict[str, dict[str, Any]] = {}
    for row in media_inputs:
        if isinstance(row, dict) and row.get("id"):
            by_id[str(row["id"])] = row
    word_map_all = _load_word_map_all(word_map_all_path)

    seg_files = sorted(sdir.glob("refiner_segment_output_*.txt"))
    if not seg_files:
        raise FileNotFoundError(f"No segment output txt files found in {sdir}")

    visual_actions: list[dict[str, Any]] = []
    caption_jobs: list[dict[str, Any]] = []
    canvas = {"width": 1080, "height": 1920, "fps": 30, "duration": 30.0}
    for p in seg_files:
        obj = _load_segment_json_from_text(p)
        if not isinstance(obj, dict):
            continue
        cv = obj.get("canvas")
        if isinstance(cv, dict):
            canvas["width"] = int(float(cv.get("width", canvas["width"]) or canvas["width"]))
            canvas["height"] = int(float(cv.get("height", canvas["height"]) or canvas["height"]))
            canvas["fps"] = int(float(cv.get("fps", canvas["fps"]) or canvas["fps"]))
            canvas["duration"] = max(float(canvas["duration"]), float(cv.get("duration", 0.0) or 0.0))

        timeline = obj.get("final_timeline") or obj.get("visual_timeline") or []
        if isinstance(timeline, list):
            for row in timeline:
                if isinstance(row, dict):
                    visual_actions.append(row)

        cap = obj.get("caption_plan") or obj.get("caption_track") or {}
        if isinstance(cap, dict):
            cues = cap.get("cues")
            if isinstance(cues, list):
                for c in cues:
                    if not isinstance(c, dict):
                        continue
                    caption_jobs.append({"cue": c, "track": cap})

    elements: list[dict[str, Any]] = []

    # Add one main audio track (first audio-like media).
    audio_id = _pick_first_audio_id(by_id)
    if audio_id:
        audio_row = by_id[audio_id]
        dur = _probe_duration(probe.get(audio_id))
        elements.append(
            {
                "element_id": audio_id,
                "type": "music",
                "timing": {"start": 0.0, "duration": dur},
                "properties": {
                    "type": "music",
                    "source_uri": audio_row.get("path"),
                    "timing": {"start": 0.0, "duration": dur},
                },
                "actions": [{"t_start": 0.0, "t_end": dur, "op": "play", "params": {"volume": 1.0}}],
            }
        )

    # Visual elements grouped by element_id.
    by_visual_id: dict[str, list[dict[str, Any]]] = {}
    for row in visual_actions:
        eid = str(row.get("element_id", "")).strip()
        if not eid or eid not in by_id:
            continue
        media = by_id[eid]
        media_type = str(media.get("media_type", "")).lower()
        # Only true visual media should enter visual composition tracks.
        if media_type not in {"image", "video", "gif"}:
            continue
        by_visual_id.setdefault(eid, []).append(row)

    for eid, rows in by_visual_id.items():
        media = by_id[eid]
        mtype = str(media.get("media_type", "")).lower()
        etype = "gif" if mtype == "gif" else ("video" if mtype == "video" else "image")
        source_uri = media.get("path")
        actions = []
        min_start = None
        max_end = 0.0
        for r in sorted(rows, key=lambda x: float(x.get("t_start", 0.0) or 0.0)):
            ts = float(r.get("t_start", 0.0) or 0.0)
            te = float(r.get("t_end", ts) or ts)
            if te <= ts:
                continue
            min_start = ts if min_start is None else min(min_start, ts)
            max_end = max(max_end, te)
            layout = r.get("layout") if isinstance(r.get("layout"), dict) else {}
            layout = layout if isinstance(layout, dict) else {}
            probe_row = probe.get(eid) if isinstance(probe, dict) else None
            src_w, src_h = _probe_size(probe_row)
            lx = _to_float(layout.get("x"), _to_float(r.get("x"), 0.0))
            ly = _to_float(layout.get("y"), _to_float(r.get("y"), 0.0))
            lw = _to_float(layout.get("width"), _to_float(r.get("width"), float(src_w)))
            lh = _to_float(layout.get("height"), _to_float(r.get("height"), float(src_h)))
            fit = str(layout.get("fit") or r.get("fit") or "cover").lower()
            # Renderer expects center-based x/y coordinates.
            cx = lx + (lw / 2.0)
            cy = ly + (lh / 2.0)
            scale = _compute_scale(src_w=src_w, src_h=src_h, target_w=lw, target_h=lh, fit=fit)
            transition_in = r.get("transition_in") if isinstance(r.get("transition_in"), dict) else {}
            transition_out = r.get("transition_out") if isinstance(r.get("transition_out"), dict) else {}
            fade_in_s = _transition_to_fade_seconds(transition_in)
            fade_out_s = _transition_to_fade_seconds(transition_out)
            actions.append(
                {
                    "t_start": round(ts, 3),
                    "t_end": round(te, 3),
                    "op": "show",
                    "params": _drop_nones(
                        {
                            "x": round(cx, 3),
                            "y": round(cy, 3),
                            # Keep visual fixed at center unless explicitly provided.
                            "from_x": round(cx, 3),
                            "from_y": round(cy, 3),
                            "scale": round(scale, 6),
                            "motion_ease": "linear",
                            "trim_in": 0.0,
                            "trim_out": round(max(0.0, te - ts), 3),
                            "fade_in_s": fade_in_s,
                            "fade_out_s": fade_out_s,
                        }
                    ),
                }
            )
        if not actions:
            continue
        elements.append(
            {
                "element_id": eid,
                "type": etype,
                "timing": {"start": round(min_start or 0.0, 3), "duration": round(max_end - (min_start or 0.0), 3)},
                "properties": {"type": etype, "source_uri": source_uri, "timing": {"start": round(min_start or 0.0, 3), "duration": round(max_end - (min_start or 0.0), 3)}},
                "actions": actions,
            }
        )

    # Caption track from cues (strictly from segment outputs; no inferred cues).
    if caption_jobs:
        norm_cues = _normalize_caption_jobs(caption_jobs)
        if not norm_cues:
            norm_cues = []
        if norm_cues:
            start = norm_cues[0]["t_start"]
            end = norm_cues[-1]["t_end"]
        else:
            start, end = 0.0, 0.0
        caption_actions = []
        for cue in norm_cues:
            params = cue["params"]
            cue_text = str(params.get("text", ""))
            seq = _build_word_sequence_for_cue(cue_text, cue["t_start"], cue["t_end"], word_map_all)
            if seq:
                params["word_timing_sequence"] = seq
            caption_actions.append(
                {
                    "t_start": cue["t_start"],
                    "t_end": cue["t_end"],
                    "op": "show",
                    "params": params,
                }
            )
        cap_props = _drop_nones(
            {
                "type": "caption",
                "timing": {"start": round(start, 3), "duration": round(max(0.0, end - start), 3)},
                "transform": {
                    "x": norm_cues[0]["params"].get("x", 540.0),
                    "y": norm_cues[0]["params"].get("y", 1600.0),
                },
                "font_size": norm_cues[0]["params"].get("font_size"),
                "font_weight": norm_cues[0]["params"].get("font_weight"),
                "font_family": norm_cues[0]["params"].get("font_family"),
                "color": norm_cues[0]["params"].get("color"),
                "stroke_color": norm_cues[0]["params"].get("stroke_color"),
                "stroke_width": norm_cues[0]["params"].get("stroke_width"),
            }
        )
        elements.append(
            {
                "element_id": "caption_track_1",
                "type": "caption",
                "timing": {"start": round(start, 3), "duration": round(max(0.0, end - start), 3)},
                "properties": cap_props,
                "actions": caption_actions,
            }
        )

    inter = {
        "version": "1.1",
        "video": {
            "size": {"width": int(canvas["width"]), "height": int(canvas["height"])},
            "fps": int(canvas["fps"]),
            "bg_color": [0, 0, 0],
            "output_path": str(video_path).replace("\\", "/"),
            "metadata": {
                "design_events": _collect_screen_bg_events(seg_files),
            },
        },
        "properties_path": None,
        "elements": elements,
    }

    inter_path.parent.mkdir(parents=True, exist_ok=True)
    inter_path.write_text(json.dumps(inter, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        render_from_json(str(inter_path), strict=True)
    except subprocess.CalledProcessError as exc:
        if "Cannot allocate memory" not in str(exc):
            raise
        print("[A2V_PIPELINE][RENDER] FFmpeg OOM detected, retrying with simplified caption rendering.")
        inter_simple = _simplify_inter_for_low_memory(inter)
        inter_path.write_text(json.dumps(inter_simple, ensure_ascii=False, indent=2), encoding="utf-8")
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
    out: list[dict[str, Any]] = []
    for row in caption_jobs:
        cue = row.get("cue") if isinstance(row.get("cue"), dict) else {}
        track = row.get("track") if isinstance(row.get("track"), dict) else {}
        try:
            ts = round(float(cue.get("t_start", cue.get("start", 0.0)) or 0.0), 3)
            te = round(float(cue.get("t_end", cue.get("end", ts)) or ts), 3)
        except Exception:
            continue
        if te <= ts:
            continue
        text = str(cue.get("text", ""))
        layout = track.get("layout") if isinstance(track.get("layout"), dict) else {}
        style = track.get("style") if isinstance(track.get("style"), dict) else {}
        anim = track.get("animation") if isinstance(track.get("animation"), dict) else {}
        style_override = cue.get("style_override") if isinstance(cue.get("style_override"), dict) else {}
        # track layout is top-left box; cue can override y per-group.
        lx = _to_float(layout.get("x"), 90.0)
        ly = _to_float(layout.get("y"), 1450.0)
        lw = _to_float(layout.get("width"), 900.0)
        lh = _to_float(layout.get("height"), 300.0)
        cx = lx + (lw / 2.0)
        cue_y = cue.get("y")
        if cue_y is not None:
            cy = _to_float(cue_y, ly + (lh / 2.0))
        else:
            cy = ly + (lh / 2.0)
        color = style_override.get("text_color", style.get("text_color"))
        bg = style_override.get("background_color", style.get("background_color"))
        highlight_words = cue.get("highlight_words") if isinstance(cue.get("highlight_words"), list) else None
        has_highlight = bool(highlight_words)
        params = _drop_nones(
            {
                "text": text,
                "x": round(cx, 3),
                "y": round(cy, 3),
                "font_family": style.get("font_family"),
                "font_size": _extract_font_size(style),
                "font_weight": style.get("font_weight"),
                # Keep base color stable; per-word highlight is handled at render time
                # via word_timing_sequence + important_words.
                "color": color,
                "highlight_color": style.get("highlight_color"),
                "stroke_color": "#000000",
                "stroke_width": 3,
                "caption_animation": anim.get("type"),
                "caption_mode": "word_reveal_v2",
                "background_opacity": _rgba_opacity(bg),
                "background_color": _rgba_color(bg),
                "important_words": highlight_words,
            }
        )
        out.append({"t_start": ts, "t_end": te, "params": params})
    out.sort(key=lambda x: x["t_start"])
    return out


def _pick_first_audio_id(by_id: dict[str, dict[str, Any]]) -> str | None:
    for eid, row in by_id.items():
        if str(row.get("media_type", "")).lower() in {"audio", "music", "sfx"}:
            return eid
    return None


def _probe_duration(row: Any) -> float:
    if not isinstance(row, dict):
        return 30.0
    try:
        d = float(row.get("duration") or 30.0)
        return round(d, 3)
    except Exception:
        return 30.0


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
        obj = _load_segment_json_from_text(p)
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


def _extract_font_size(style: dict[str, Any]) -> int | None:
    raw = style.get("font_size")
    if raw is None:
        rule = style.get("font_size_rule")
        if isinstance(rule, str):
            m = re.search(r"(\d+)", rule)
            if m:
                raw = m.group(1)
    try:
        return int(float(raw)) if raw is not None else None
    except Exception:
        return None


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
