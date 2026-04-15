from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure repo root is on sys.path when running this file directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vasp.core.elements import Caption, Figure, GIF, Image, Music, Sfx, Timing, Video
from vasp.assets.semantic_library import resolve_semantic_sfx


def _color_hex(rgb: list[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _escape_text(text: str) -> str:
    # Normalize apostrophes to avoid drawtext quote-break issues on ffmpeg 4.x.
    text = text.replace("'", "")
    return (
        text.replace("\n", " ")
        .replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace(";", r"\;")
        .replace("%", r"\%")
    )


def _escape_fontfile(path: str) -> str:
    # ffmpeg filter parser expects escaped drive colon and forward slashes.
    return path.replace("\\", "/").replace(":", r"\:")


def _safe_drawtext_color(color: object, fallback: str = "0xFFFFFF") -> str:
    value = str(color or "").strip()
    if not value:
        return fallback
    if value.startswith("#") and len(value) in (7, 9):
        return "0x" + value[1:]
    return value


def _to_int(value: object, default: int) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _normalized_duration(value: float, *, min_value: float = 0.02) -> float:
    """Clamp tiny floating-point durations that ffmpeg trim rejects."""
    if value < min_value:
        return 0.0
    return round(value, 6)


def _run_ffmpeg_with_filter(cmd_prefix: list[str], filter_graph: str, cmd_suffix: list[str]) -> None:
    """
    Run ffmpeg with either -filter_complex or -filter_complex_script.
    This avoids Windows command-length failures for long filter graphs.
    """
    # Use script file when filter graph is large (or contains many chained operations).
    use_script = len(filter_graph) > 6000
    if not use_script:
        print(f"[RENDER] ffmpeg inline filter graph size={len(filter_graph)}")
        subprocess.run(cmd_prefix + ["-filter_complex", filter_graph] + cmd_suffix, check=True)
        return

    with tempfile.NamedTemporaryFile("w", suffix=".ffgraph", delete=False, encoding="utf-8") as handle:
        handle.write(filter_graph)
        graph_path = handle.name
    debug_graph_path = ROOT / "output" / "last_filter.ffgraph"
    try:
        debug_graph_path.parent.mkdir(parents=True, exist_ok=True)
        debug_graph_path.write_text(filter_graph, encoding="utf-8")
        print(f"[RENDER] Debug filter graph copy: {debug_graph_path}")
    except OSError:
        pass
    try:
        print(f"[RENDER] ffmpeg filter graph too large ({len(filter_graph)}), using script: {graph_path}")
        subprocess.run(cmd_prefix + ["-filter_complex_script", graph_path] + cmd_suffix, check=True)
    finally:
        Path(graph_path).unlink(missing_ok=True)


def _coarsen_actions(actions: list[dict], max_actions: int) -> list[dict]:
    """Reduce action count while preserving timeline coverage."""
    if len(actions) <= max_actions:
        return actions
    keep: list[dict] = []
    stride = len(actions) / float(max_actions)
    for i in range(max_actions):
        idx = min(len(actions) - 1, int(round(i * stride)))
        keep.append(actions[idx])
    # Re-sort and de-duplicate exact start/end duplicates.
    keep = sorted(keep, key=lambda a: (a.get("t_start", 0.0), a.get("t_end", 0.0)))
    dedup: list[dict] = []
    seen: set[tuple[float, float]] = set()
    for a in keep:
        key = (float(a.get("t_start", 0.0)), float(a.get("t_end", 0.0)))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(a)
    return dedup


def _video_size(payload: dict) -> tuple[int, int]:
    video = payload.get("video", {})
    size = video.get("size") or {}
    width = int(size.get("width", 1080))
    height = int(size.get("height", 1920))
    return width, height


def _video_fps(payload: dict) -> int:
    video = payload.get("video", {})
    return int(video.get("fps", 30))


def _video_bg(payload: dict) -> str:
    video = payload.get("video", {})
    return _color_hex(video.get("bg_color", [0, 0, 0]))


def _collect_transcript_words(payload: dict) -> list[dict]:
    media_context = payload.get("media_context", {})
    if not isinstance(media_context, dict):
        return []
    analysis = media_context.get("analysis", {})
    if not isinstance(analysis, dict):
        return []
    words: list[dict] = []
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        for item in transcript.get("words", []) or []:
            if isinstance(item, dict):
                words.append(item)
    return words


def _resolve_moment_time(payload: dict, moment: str) -> tuple[float | None, float | None]:
    needle = re.sub(r"\s+", " ", str(moment).strip().lower())
    if not needle:
        return None, None
    words = _collect_transcript_words(payload)
    if not words:
        return None, None
    # Try phrase match on transcript window.
    phrase_tokens = needle.split(" ")
    word_texts = [str(w.get("text", "")).strip().lower() for w in words]
    for i in range(0, max(0, len(word_texts) - len(phrase_tokens) + 1)):
        if word_texts[i : i + len(phrase_tokens)] == phrase_tokens:
            start = _safe_float(words[i].get("start"))
            end = _safe_float(words[i + len(phrase_tokens) - 1].get("end"))
            if start is not None and end is not None:
                return start, end
    # Fallback to first token contains match.
    for w in words:
        text = str(w.get("text", "")).strip().lower()
        if needle in text:
            start = _safe_float(w.get("start"))
            end = _safe_float(w.get("end"))
            return start, end
    return None, None


def _resolve_semantic_actions(payload: dict, actions: list[dict]) -> list[dict]:
    resolved: list[dict] = []
    for action in actions:
        params = action.get("params", {}) if isinstance(action.get("params", {}), dict) else {}
        moment = params.get("moment_text") or params.get("moment")
        if not moment:
            resolved.append(action)
            continue
        start, end = _resolve_moment_time(payload, str(moment))
        if start is None or end is None:
            resolved.append(action)
            continue
        duration = _safe_float(params.get("duration")) or max(0.12, end - start)
        out = dict(action)
        out["t_start"] = float(start)
        out["t_end"] = float(start + duration)
        resolved.append(out)
    return resolved


def _background_style(payload: dict) -> str:
    video = payload.get("video", {})
    if not isinstance(video, dict):
        return ""
    style = str(video.get("background_style", "")).strip().lower()
    if style:
        return style
    metadata = video.get("metadata", {})
    if isinstance(metadata, dict):
        return str(metadata.get("background_style", "")).strip().lower()
    return ""


def _build_base_video_filter(payload: dict) -> str:
    """
    Build the base video chain ending with [base0], including background style
    and optional timed design overlays from video.metadata.design_events.
    """
    style = _background_style(payload)
    chain: list[str] = ["setpts=PTS-STARTPTS"]

    # Style presets (kept ffmpeg-4.x friendly).
    if "calendar" in style or style in {"parchment", "parchment_dark"}:
        chain.extend(
            [
                "drawgrid=w=120:h=120:t=2:c=#3a3a3a@0.35",
                "eq=brightness=-0.03:saturation=0.9",
            ]
        )
    elif "grain" in style and "vignette" in style:
        chain.extend(["noise=alls=10:allf=t+u", "vignette=PI/4"])
    elif style in {"cinematic_red", "history_red"}:
        chain.extend(["noise=alls=8:allf=t+u", "drawbox=x=0:y=0:w=iw:h=ih:color=#4a0d0d@0.26:t=fill", "vignette=PI/5"])
    elif style in {"night_blue", "kepler_night", "starfield", "starry_night"}:
        chain.extend(
            [
                "drawbox=x=0:y=0:w=iw:h=ih:color=#0b1f44@0.24:t=fill",
                "vignette=PI/5",
            ]
        )
    elif style in {"map_blue", "map_grid"}:
        chain.extend(
            [
                "drawbox=x=0:y=0:w=iw:h=ih:color=#0b1f44@0.24:t=fill",
                "drawgrid=w=180:h=180:t=1:c=#84a8ff@0.10",
                "vignette=PI/5",
            ]
        )
    elif style in {"morning_energy", "sunrise_warm", "sunrise", "morning"}:
        chain.extend(
            [
                "drawbox=x=0:y=0:w=iw:h=ih:color=#ffd7a8@0.26:t=fill",
                "drawbox=x=0:y=ih*0.55:w=iw:h=ih*0.45:color=#ffb36b@0.20:t=fill",
                "eq=brightness=0.03:saturation=1.08",
                "vignette=PI/7",
            ]
        )
    elif style in {"mint_daylight", "fresh_daylight", "teal_daylight"}:
        chain.extend(
            [
                "drawbox=x=0:y=0:w=iw:h=ih:color=#bff7e8@0.24:t=fill",
                "drawbox=x=0:y=ih*0.50:w=iw:h=ih*0.50:color=#8fe7d1@0.14:t=fill",
                "eq=brightness=0.02:saturation=1.02",
                "vignette=PI/8",
            ]
        )
    elif style in {"sky_breeze", "blue_morning", "energy_blue"}:
        chain.extend(
            [
                "drawbox=x=0:y=0:w=iw:h=ih:color=#b8dcff@0.23:t=fill",
                "drawbox=x=0:y=ih*0.58:w=iw:h=ih*0.42:color=#86c6ff@0.14:t=fill",
                "eq=brightness=0.02:saturation=1.04",
                "vignette=PI/8",
            ]
        )
    elif "roman" in style or "column" in style:
        chain.extend(
            [
                "drawbox=x=120:y=0:w=70:h=ih:color=#777777@0.18:t=fill",
                "drawbox=x=320:y=0:w=70:h=ih:color=#777777@0.14:t=fill",
                "drawbox=x=760:y=0:w=70:h=ih:color=#777777@0.14:t=fill",
            ]
        )
    elif style in {"clean_cinematic", "charcoal", "clean_black", "neutral_dark"}:
        chain.extend(["drawbox=x=0:y=0:w=iw:h=ih:color=#0f1117@0.15:t=fill", "vignette=PI/6"])
    elif style in {"clean_white", "white_minimal"}:
        chain.extend(["drawbox=x=0:y=0:w=iw:h=ih:color=#ffffff@0.92:t=fill", "eq=brightness=0.01:saturation=0.92"])
    elif style in {"white_pattern", "paper_light"}:
        chain.extend(
            [
                "drawbox=x=0:y=0:w=iw:h=ih:color=#ffffff@0.92:t=fill",
                "drawgrid=w=220:h=220:t=1:c=#d8d8d8@0.20",
                "eq=brightness=0.01:saturation=0.90",
            ]
        )

    # Optional timed design overlays.
    video = payload.get("video", {})
    metadata = video.get("metadata", {}) if isinstance(video, dict) else {}
    events = metadata.get("design_events", []) if isinstance(metadata, dict) else []
    if isinstance(events, list):
        for ev in events:
            if not isinstance(ev, dict):
                continue
            t_start = _safe_float(ev.get("t_start"))
            t_end = _safe_float(ev.get("t_end"))
            if t_start is None or t_end is None or t_end <= t_start:
                continue
            enable = f"between(t\\,{t_start}\\,{t_end})"
            ev_type = str(ev.get("type", "panel")).lower()
            color = str(ev.get("color", "#ffffff"))
            alpha = float(ev.get("opacity", 0.18) or 0.18)
            draw_color = f"{color}@{max(0.0, min(alpha, 1.0))}"
            if ev_type == "tint":
                chain.append(f"drawbox=x=0:y=0:w=iw:h=ih:color={draw_color}:t=fill:enable='{enable}'")
            elif ev_type == "frame":
                thickness = _to_int(ev.get("thickness", 18), 18)
                chain.append(f"drawbox=x=0:y=0:w=iw:h={thickness}:color={draw_color}:t=fill:enable='{enable}'")
                chain.append(f"drawbox=x=0:y=ih-{thickness}:w=iw:h={thickness}:color={draw_color}:t=fill:enable='{enable}'")
                chain.append(f"drawbox=x=0:y=0:w={thickness}:h=ih:color={draw_color}:t=fill:enable='{enable}'")
                chain.append(f"drawbox=x=iw-{thickness}:y=0:w={thickness}:h=ih:color={draw_color}:t=fill:enable='{enable}'")
            elif ev_type == "grid":
                cell_w = _to_int(ev.get("cell_w", 120), 120)
                cell_h = _to_int(ev.get("cell_h", 120), 120)
                thickness = _to_int(ev.get("thickness", 2), 2)
                chain.append(f"drawgrid=w={cell_w}:h={cell_h}:t={thickness}:c={draw_color}:enable='{enable}'")
            elif ev_type == "stripe_h":
                band_h = _to_int(ev.get("band_h", 120), 120)
                gap_h = _to_int(ev.get("gap_h", 260), 260)
                chain.append(
                    f"drawbox=x=0:y=mod(t*60\\,{gap_h}):w=iw:h={band_h}:color={draw_color}:t=fill:enable='{enable}'"
                )
            elif ev_type == "stripe_v":
                band_w = _to_int(ev.get("band_w", 120), 120)
                gap_w = _to_int(ev.get("gap_w", 300), 300)
                chain.append(
                    f"drawbox=x=mod(t*70\\,{gap_w}):y=0:w={band_w}:h=ih:color={draw_color}:t=fill:enable='{enable}'"
                )
            else:
                # panel
                x = str(ev.get("x", "0"))
                y = str(ev.get("y", "0"))
                w = str(ev.get("w", "iw"))
                h = str(ev.get("h", "ih"))
                chain.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={draw_color}:t=fill:enable='{enable}'")

    return f"[0:v]{','.join(chain)}[base0]"


def _write_output_json(input_path: Path, payload: dict) -> Path:
    out_path = input_path.with_name(input_path.stem + "_output.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return out_path


def _overlay_xy_center(x: float, y: float) -> tuple[str, str]:
    """Treat x,y as center; return overlay expressions for top-left."""
    return (f"{x}-overlay_w/2", f"{y}-overlay_h/2")


def _escape_filter_expr(expr: str) -> str:
    # FFmpeg filter option parser treats commas as separators inside expressions.
    return expr.replace(",", r"\,")


def _overlay_xy_motion(
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    t_start: float,
    t_end: float,
    ease: str = "linear",
) -> tuple[str, str]:
    """Return motion expressions (center-based) for overlay x/y."""
    span = max(0.0001, t_end - t_start)
    norm = f"((t-{t_start})/{span})"
    ease_name = str(ease).lower()
    if ease_name in {"smooth", "ease", "ease_in_out", "smoothstep"}:
        # smoothstep(u) = u*u*(3-2*u), with clamp to [0,1]
        u = f"clip({norm},0,1)"
        p = f"(({u})*({u})*(3-2*({u})))"
    elif ease_name in {"bounce", "bounce_out", "ease_out_bounce"}:
        # Catchier but smooth bounce-out curve with decaying oscillation.
        # p(0)=0, p(1)=1 and slight overshoot in between.
        u = f"clip({norm},0,1)"
        p = f"(1-pow(1-({u}),2)*cos(8*PI*({u}))*(1-({u})))"
    elif ease_name in {"pop", "overshoot"}:
        u = f"clip({norm},0,1)"
        p = f"(1-pow(1-({u}),3)*(1+1.2*({u})))"
    elif ease_name in {"elastic", "spring"}:
        u = f"clip({norm},0,1)"
        p = f"(1-pow(2,-10*({u}))*cos(8*PI*({u})))"
    elif ease_name in {"slide_up", "slide_down", "slide_left", "slide_right"}:
        u = f"clip({norm},0,1)"
        p = f"(({u})*({u})*(3-2*({u})))"
    else:
        p = norm
    x = f"({from_x}+({to_x}-{from_x})*({p}))-overlay_w/2"
    y = f"({from_y}+({to_y}-{from_y})*({p}))-overlay_h/2"
    return x, y


def _time_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def _caption_priority(job: dict) -> tuple[float, int]:
    # Prefer explicit priority; otherwise prefer longer text and larger font.
    params = job.get("params", {})
    text = str(params.get("text", ""))
    font_size = _to_int(params.get("font_size", 48), 48)
    priority = float(params.get("caption_priority", 0.0) or 0.0)
    return (priority + (font_size / 1000.0), len(text))


def _suppress_overlapping_caption_jobs(jobs: list[dict]) -> list[dict]:
    """
    Prevent double-caption overlays at the same placement/time window.
    Keep only one caption when jobs overlap heavily around same x/y.
    """
    kept: list[dict] = []
    for job in sorted(jobs, key=lambda j: (j["t_start"], j["t_end"])):
        jx = float(job.get("x", 0.0))
        jy = float(job.get("y", 0.0))
        replaced = False
        for idx, existing in enumerate(kept):
            ex = float(existing.get("x", 0.0))
            ey = float(existing.get("y", 0.0))
            close_pos = abs(jx - ex) <= 20.0 and abs(jy - ey) <= 40.0
            if not close_pos:
                continue
            # Don't suppress sequential actions from the same caption element track.
            if str(job.get("element_id")) == str(existing.get("element_id")):
                continue
            if not _time_overlap(job["t_start"], job["t_end"], existing["t_start"], existing["t_end"]):
                continue
            if _caption_priority(job) > _caption_priority(existing):
                kept[idx] = job
            replaced = True
            break
        if not replaced:
            kept.append(job)
    return kept


def _normalize_caption_jobs(jobs: list[dict]) -> list[dict]:
    """
    Normalize caption timeline inside each element track:
    - If neighboring items in same track have tiny overlaps, trim previous end.
    - If there is a tiny gap, keep as-is (renderer can handle).
    """
    by_track: dict[str, list[dict]] = {}
    for job in jobs:
        track = str(job.get("element_id", "caption"))
        by_track.setdefault(track, []).append(job)

    out: list[dict] = []
    for track_jobs in by_track.values():
        track_jobs = sorted(track_jobs, key=lambda j: (j["t_start"], j["t_end"]))
        for i in range(len(track_jobs) - 1):
            cur = track_jobs[i]
            nxt = track_jobs[i + 1]
            overlap = float(cur["t_end"]) - float(nxt["t_start"])
            if 0.0 < overlap <= 0.12:
                cur["t_end"] = float(nxt["t_start"])
        for job in track_jobs:
            if float(job["t_end"]) > float(job["t_start"]):
                out.append(job)
    return sorted(out, key=lambda j: (j["t_start"], j["t_end"]))


def _resolve_caption_position(
    params: dict,
    width: int,
    height: int,
    default_x: float,
    default_y: float,
) -> tuple[float, float]:
    def _clamp_anchor(px: float, py: float) -> tuple[float, float]:
        # Keep caption anchor inside a conservative 9:16 safe zone.
        min_x = width * 0.10
        max_x = width * 0.90
        min_y = height * 0.10
        max_y = height * 0.90
        return max(min_x, min(max_x, px)), max(min_y, min(max_y, py))

    placement = str(
        params.get("caption_placement", params.get("placement", params.get("position", "")))
    ).strip().lower()
    x = float(params.get("x", default_x))
    y = float(params.get("y", default_y))
    if not placement:
        return _clamp_anchor(x, y)
    if placement in {"bottom_safe", "bottom_center_safe_zone", "lower_safe"}:
        return _clamp_anchor(width * 0.5, height * 0.86)
    if placement in {"lower_third", "bottom_center"}:
        return _clamp_anchor(width * 0.5, height * 0.80)
    if placement in {"middle", "center"}:
        return _clamp_anchor(width * 0.5, height * 0.50)
    if placement in {"top_safe", "upper_third"}:
        return _clamp_anchor(width * 0.5, height * 0.18)
    if placement in {"left_lower"}:
        return _clamp_anchor(width * 0.40, height * 0.82)
    if placement in {"right_lower"}:
        return _clamp_anchor(width * 0.60, height * 0.82)
    return _clamp_anchor(x, y)


def _clamp_caption_font_size(font_size: int, text: str, width: int) -> int:
    """
    Keep captions inside frame by estimating line width from glyph count.
    Prevents oversized text spilling outside 9:16 bounds.
    """
    safe_width = max(300, int(width * 0.84))
    lines = [ln for ln in str(text).split("\n") if ln.strip()] or [str(text)]
    longest = max(len(ln) for ln in lines)
    # Rough sans-serif width estimate per glyph.
    est = max(0.52, min(0.62, 0.56 + (0.02 if longest < 10 else -0.02)))
    max_fs = int(safe_width / max(1.0, longest * est))
    max_fs = max(24, min(120, max_fs))
    return max(24, min(int(font_size), max_fs))


def _fit_caption_center_x(x_local: float, text: str, font_size: int, width: int) -> float:
    """
    Clamp caption center x so estimated rendered text stays inside frame.
    """
    lines = [ln for ln in str(text).split("\n") if ln.strip()] or [str(text)]
    longest = max(len(ln) for ln in lines)
    est_half = max(40.0, (longest * max(24, font_size) * 0.56) / 2.0)
    margin = 24.0
    min_x = est_half + margin
    max_x = width - est_half - margin
    if min_x > max_x:
        return width * 0.5
    return max(min_x, min(max_x, x_local))


def _caption_anim_exprs(
    anim: str,
    x_local: float,
    y_local: float,
    t_start: float,
    t_end: float,
    intro_dur: float,
) -> tuple[str, str, str]:
    """
    Return x/y/alpha expressions for animated caption entrance.
    """
    p = f"(clip((t-{t_start})/{max(0.01, intro_dur)}\\,0\\,1))"
    smooth = f"(({p})*({p})*(3-2*({p})))"
    base_x = f"{x_local}-text_w/2"
    base_y = f"{y_local}-text_h/2"
    alpha = smooth
    anim = (anim or "").strip().lower()
    if anim in {"slide_up", "rise"}:
        y_expr = f"{base_y}+(1-({smooth}))*64"
        return base_x, y_expr, alpha
    if anim in {"slide_left"}:
        x_expr = f"{base_x}+(1-({smooth}))*80"
        return x_expr, base_y, alpha
    if anim in {"slide_right"}:
        x_expr = f"{base_x}-(1-({smooth}))*80"
        return x_expr, base_y, alpha
    if anim in {"zoom_in", "zoom"}:
        x_expr = f"{base_x}+(1-({smooth}))*18"
        y_expr = f"{base_y}+(1-({smooth}))*18"
        return x_expr, y_expr, f"pow({smooth}\\,0.7)"
    if anim in {"bounce", "bounce_in", "pop_bounce"}:
        # Damped overshoot on y and quick opacity ramp.
        y_expr = f"{base_y}+(1-({smooth}))*90-16*sin((t-{t_start})*38)*exp(-8*(t-{t_start}))"
        return base_x, y_expr, alpha
    if anim in {"wobble", "swing"}:
        x_expr = f"{base_x}+10*sin((t-{t_start})*26)*exp(-6*(t-{t_start}))"
        y_expr = f"{base_y}+5*sin((t-{t_start})*20)*exp(-6*(t-{t_start}))"
        return x_expr, y_expr, alpha
    if anim in {"elastic"}:
        x_expr = f"{base_x}+(1-({smooth}))*48*sin((t-{t_start})*22)*exp(-7*(t-{t_start}))"
        return x_expr, base_y, alpha
    if anim in {"shake", "impact"}:
        x_expr = f"{base_x}+sin((t-{t_start})*95)*10*exp(-10*(t-{t_start}))"
        return x_expr, base_y, alpha
    # Default pop/fade.
    return base_x, base_y, alpha


def _render_caption_words(payload: dict, output_path: Path, element: dict, actions: list[dict]) -> None:
    width, height = _video_size(payload)
    fps = _video_fps(payload)
    bg_color = _video_bg(payload)
    text = element["text"]

    words = text.split()
    colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4"]
    rng = random.Random(42)

    seed = 42
    for action in actions:
        if action.get("op") == "word_scatter_color":
            seed = int(action.get("params", {}).get("seed", 42))
            break
    rng = random.Random(seed)

    caption_objects: list[Caption] = []
    for idx, word in enumerate(words):
        start = float(element["timing"]["start"])
        duration = float(element["timing"]["duration"])
        x = rng.uniform(0, width)
        y = rng.uniform(0, height)
        caption_objects.append(
            Caption(
                id=f"{element['id']}_word_{idx}",
                timing=Timing(start=start, duration=duration),
                text=word,
                language=element.get("language"),
                metadata={"word_index": idx, "color": colors[idx % len(colors)]},
                transform={"x": x, "y": y},
            )
        )

    output_payload = {"captions": [caption.model_dump() for caption in caption_objects]}
    _write_output_json(Path(payload["_input_path"]), output_payload)

    duration = float(element["timing"]["duration"])
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    fontfile = _escape_fontfile(str(font_path)) if font_path.exists() else ""

    filters = []
    for caption in output_payload["captions"]:
        text = _escape_text(caption["text"])
        x = caption["transform"]["x"]
        y = caption["transform"]["y"]
        x_expr = f"{x}-text_w/2"
        y_expr = f"{y}-text_h/2"
        color = caption.get("metadata", {}).get("color", "#FFFFFF")
        start = caption["timing"]["start"]
        end = start + caption["timing"]["duration"]
        enable = f"between(t\\,{start}\\,{end})"
        font_part = f"fontfile='{fontfile}':" if fontfile else ""
        drawtext = (
            f"drawtext={font_part}"
            f"text='{text}':"
            f"x={x_expr}:y={y_expr}:"
            f"fontcolor={color}:"
            f"fontsize=48:"
            f"enable='{enable}'"
        )
        filters.append(drawtext)

    vf = ",".join(filters)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def _render_overlay_media(
    payload: dict,
    output_path: Path,
    media_path: Path,
    element: dict,
    *,
    is_image: bool = False,
    actions: list[dict] | None = None,
) -> None:
    width, height = _video_size(payload)
    fps = _video_fps(payload)
    bg_color = _video_bg(payload)
    duration = float(element["timing"]["duration"])
    x = element.get("transform", {}).get("x", 0)
    y = element.get("transform", {}).get("y", 0)
    x_expr, y_expr = _overlay_xy_center(x, y)

    # If actions provided, build time-based overlays (supports trim_in/out).
    final_video_label: str | None = None
    if actions:
        filters = [_build_base_video_filter(payload)]
        base_label = "base0"
        prev_x = float(x)
        prev_y = float(y)
        for idx, action in enumerate(actions):
            if action.get("op") != "show":
                continue
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            scale = float(params.get("scale", 1.0))
            action_x = float(params.get("x", prev_x))
            action_y = float(params.get("y", prev_y))
            motion_from_x = float(params.get("from_x", prev_x))
            motion_from_y = float(params.get("from_y", prev_y))
            action_x_expr, action_y_expr = _overlay_xy_motion(
                motion_from_x,
                motion_from_y,
                action_x,
                action_y,
                t_start,
                t_end,
                ease=str(params.get("motion_ease", "smooth")),
            )
            action_x_expr = _escape_filter_expr(action_x_expr)
            action_y_expr = _escape_filter_expr(action_y_expr)
            trim_in = float(params.get("trim_in", 0.0))
            trim_out = params.get("trim_out")
            length = element.get("length")
            if length is not None:
                trim_out = min(float(trim_out) if trim_out is not None else float(length), float(length))
            seg_dur = max(0.0, t_end - t_start)
            if trim_out is not None:
                seg_dur = min(seg_dur, max(0.0, float(trim_out) - trim_in))
            seg_dur = _normalized_duration(seg_dur)
            if seg_dur <= 0.0:
                continue
            label = f"ov{idx}"
            filters.append(
                f"[1:v]trim=start={trim_in}:duration={seg_dur},setpts=PTS-STARTPTS,"
                f"scale=iw*{scale}:ih*{scale}[{label}]"
            )
            out_label = f"v{idx}"
            filters.append(
                f"[{base_label}][{label}]overlay={action_x_expr}:{action_y_expr}:enable='between(t\\,{t_start}\\,{t_end})'[{out_label}]"
            )
            base_label = out_label
            prev_x = action_x
            prev_y = action_y
        filter_str = ";".join(filters)
        final_video_label = base_label
    else:
        filter_str = f"[1:v]scale=iw:ih[ov];[0:v][ov]overlay={x_expr}:{y_expr}"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
    ]
    if is_image:
        cmd += ["-loop", "1", "-t", str(duration), "-i", str(media_path)]
    else:
        cmd += ["-i", str(media_path)]
    cmd += [
        "-filter_complex",
        filter_str,
    ]
    if final_video_label is not None:
        cmd += ["-map", f"[{final_video_label}]"]
    cmd += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def _render_image_actions(
    payload: dict, output_path: Path, media_path: Path, actions: list[dict], element: dict
) -> bool:
    crop_action = next((a for a in actions if a.get("op") == "crop"), None)
    pad_action = next((a for a in actions if a.get("op") == "pad"), None)
    if not crop_action:
        return False

    width, height = _video_size(payload)
    fps = _video_fps(payload)
    bg_color = _video_bg(payload)
    duration = float(element["timing"]["duration"])
    x = element.get("transform", {}).get("x", 0)
    y = element.get("transform", {}).get("y", 0)
    x_expr, y_expr = _overlay_xy_center(x, y)

    crop = crop_action.get("params", {})
    crop_w = crop.get("width_ratio", 1.0)
    crop_h = crop.get("height_ratio", 1.0)
    crop_x = crop.get("x", 0)
    crop_y = crop.get("y", 0)

    pad = (pad_action or {}).get("params", {})
    pad_top = pad.get("top", 0)
    pad_right = pad.get("right", 0)
    pad_bottom = pad.get("bottom", 0)
    pad_left = pad.get("left", 0)

    t1_start = float(crop_action.get("t_start", 0.0))
    t1_end = float(crop_action.get("t_end", duration))
    if pad_action:
        t2_start = float(pad_action.get("t_start", t1_end))
        t2_end = float(pad_action.get("t_end", duration))
    else:
        t2_start = t1_end
        t2_end = duration

    seg1 = f"[1:v]crop=iw*{crop_w}:ih*{crop_h}:{crop_x}:{crop_y}[c1]"
    filters = [seg1]
    ov1 = f"[0:v][c1]overlay={x_expr}:{y_expr}:enable='between(t\\,{t1_start}\\,{t1_end})'[v1]"
    filters.append(ov1)
    if pad_action:
        seg2 = (
            f"[1:v]crop=iw*{crop_w}:ih*{crop_h}:{crop_x}:{crop_y},"
            f"pad=iw+{pad_left + pad_right}:ih+{pad_top + pad_bottom}:{pad_left}:{pad_top}:"
            f"color={bg_color}[c2]"
        )
        ov2 = f"[v1][c2]overlay={x_expr}:{y_expr}:enable='between(t\\,{t2_start}\\,{t2_end})'"
        filters.extend([seg2, ov2])

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
        "-loop",
        "1",
        "-t",
        str(duration),
        "-i",
        str(media_path),
        "-filter_complex",
        ";".join(filters),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return True


def _rounded_corners_filter(radius: int) -> str:
    r = max(0, int(radius))
    if r == 0:
        return ""
    # Rounded-rectangle alpha mask based on distance from nearest edges.
    # Opaque if away from corners OR inside corner arc; transparent otherwise.
    expr = (
        "if(gte(min(X\\,W-1-X)\\,%d)+gte(min(Y\\,H-1-Y)\\,%d)"
        "\\,255\\,"
        "if(lte(pow(%d-min(X\\,W-1-X)\\,2)+pow(%d-min(Y\\,H-1-Y)\\,2)\\,pow(%d\\,2))\\,255\\,0))"
        % (r, r, r, r, r)
    )
    return f"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{expr}'"


def _fontfile_for(style: str, weight: str, family: str | None = None) -> str:
    family_key = (family or "").strip().lower()

    def pick_existing(paths: list[str]) -> Path | None:
        for p in paths:
            path = Path(p)
            if path.exists():
                return path
        return None

    # Family presets for richer caption styles.
    if family_key in {"mono", "modern_mono", "code"}:
        base = pick_existing(["C:/Windows/Fonts/CascadiaCode.ttf", "C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/arial.ttf"])
        bold = pick_existing(["C:/Windows/Fonts/CascadiaCodePL-Bold.ttf", "C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/arialbd.ttf"])
        italic = pick_existing(["C:/Windows/Fonts/consolai.ttf", "C:/Windows/Fonts/ariali.ttf"])
        bold_italic = pick_existing(["C:/Windows/Fonts/consolaz.ttf", "C:/Windows/Fonts/arialbi.ttf"])
    elif family_key in {"serif", "classic_serif"}:
        base = pick_existing(["C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/arial.ttf"])
        bold = pick_existing(["C:/Windows/Fonts/timesbd.ttf", "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/arialbd.ttf"])
        italic = pick_existing(["C:/Windows/Fonts/timesi.ttf", "C:/Windows/Fonts/georgiai.ttf", "C:/Windows/Fonts/ariali.ttf"])
        bold_italic = pick_existing(["C:/Windows/Fonts/timesbi.ttf", "C:/Windows/Fonts/georgiaz.ttf", "C:/Windows/Fonts/arialbi.ttf"])
    else:
        base = pick_existing(["C:/Windows/Fonts/arial.ttf"])
        bold = pick_existing(["C:/Windows/Fonts/arialbd.ttf"])
        italic = pick_existing(["C:/Windows/Fonts/ariali.ttf"])
        bold_italic = pick_existing(["C:/Windows/Fonts/arialbi.ttf"])

    style = (style or "normal").lower()
    weight = (weight or "regular").lower()

    if bold_italic is not None and "italic" in style and "bold" in weight:
        return _escape_fontfile(str(bold_italic))
    if italic is not None and "italic" in style:
        return _escape_fontfile(str(italic))
    if bold is not None and "bold" in weight:
        return _escape_fontfile(str(bold))
    if base is not None:
        return _escape_fontfile(str(base))
    return ""


def _audio_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_loudest_segment(audio_path: Path, duration: float, step: float = 1.0) -> float:
    if duration <= 0:
        return 0.0
    total = _audio_duration(audio_path)
    if total <= duration:
        return 0.0
    best_start = 0.0
    best_max = -9999.0
    start = 0.0
    while start + duration <= total:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(audio_path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        max_vol = None
        for line in result.stderr.splitlines():
            if "max_volume:" in line:
                try:
                    max_vol = float(line.split("max_volume:")[1].split(" dB")[0].strip())
                except ValueError:
                    max_vol = None
        if max_vol is not None and max_vol > best_max:
            best_max = max_vol
            best_start = start
        start += step
    return best_start


def _render_multi_images(
    payload: dict,
    output_path: Path,
    elements: list[dict],
    props_payload: dict,
    actions_by_id: dict[str, list[dict]],
    *,
    strict: bool,
) -> None:
    width, height = _video_size(payload)
    fps = _video_fps(payload)
    bg_color = _video_bg(payload)
    duration = max(
        (float(a.get("t_end", 0.0)) for actions in actions_by_id.values() for a in actions),
        default=0.0,
    )

    # Order elements by layer, then by original order.
    indexed = list(enumerate(elements))
    ordered = sorted(indexed, key=lambda it: (it[1].get("layer", 0), it[0]))

    # Build inputs for each element in order.
    inputs: list[Path] = []
    ordered_elements: list[dict] = []
    for _, element in ordered:
        media_path = Path(element["source_uri"])
        if not media_path.exists():
            if strict:
                raise FileNotFoundError(media_path)
            continue
        inputs.append(media_path)
        ordered_elements.append(element)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
    ]
    for media_path in inputs:
        cmd += ["-loop", "1", "-t", str(duration), "-i", str(media_path)]

    filters = [_build_base_video_filter(payload)]
    base_label = "base0"
    input_index = 1

    for element in ordered_elements:
        media_path = Path(element["source_uri"])
        if not media_path.exists():
            if strict:
                raise FileNotFoundError(media_path)
            continue
        element_id = element["id"]
        actions = sorted(actions_by_id.get(element_id, []), key=lambda a: a.get("t_start", 0.0))
        x = element.get("transform", {}).get("x", 0)
        y = element.get("transform", {}).get("y", 0)
        prev_x = float(x)
        prev_y = float(y)

        for action in actions:
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            scale = float(params.get("scale", 1.0))
            action_x = float(params.get("x", prev_x))
            action_y = float(params.get("y", prev_y))
            motion_from_x = float(params.get("from_x", prev_x))
            motion_from_y = float(params.get("from_y", prev_y))
            action_x_expr, action_y_expr = _overlay_xy_motion(
                motion_from_x,
                motion_from_y,
                action_x,
                action_y,
                t_start,
                t_end,
                ease=str(params.get("motion_ease", "smooth")),
            )
            action_x_expr = _escape_filter_expr(action_x_expr)
            action_y_expr = _escape_filter_expr(action_y_expr)
            round_corners = _to_int(params.get("round_corners", 0), 0)

            chain = f"[{input_index}:v]scale=iw*{scale}:ih*{scale}"
            rounded = _rounded_corners_filter(round_corners)
            if rounded:
                chain += f",{rounded}"
            label = f"e{element_id}_{int(t_start*1000)}"
            filters.append(f"{chain}[{label}]")
            out_label = f"v{len(filters)}"
            filters.append(
                f"[{base_label}][{label}]overlay={action_x_expr}:{action_y_expr}:enable='between(t\\,{t_start}\\,{t_end})'[{out_label}]"
            )
            base_label = out_label
            prev_x = action_x
            prev_y = action_y

        input_index += 1

    filter_graph = ";".join(filters)
    cmd_suffix = [
        "-map",
        f"[{base_label}]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    _run_ffmpeg_with_filter(cmd, filter_graph, cmd_suffix)


def _render_multi_elements(
    payload: dict,
    output_path: Path,
    elements: list[dict],
    actions_by_id: dict[str, list[dict]],
    *,
    strict: bool,
) -> Path:
    width, height = _video_size(payload)
    fps = _video_fps(payload)
    bg_color = _video_bg(payload)

    duration = max(
        (float(a.get("t_end", 0.0)) for actions in actions_by_id.values() for a in actions),
        default=0.0,
    )

    # Separate elements by type
    image_elements = [e for e in elements if e["type"] in ("image", "gif", "video")]
    caption_elements = [e for e in elements if e["type"] == "caption"]
    audio_elements = [e for e in elements if e["type"] in ("music", "sfx")]

    # Prepare inputs: base + image sources + optional audio
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
    ]

    # Image inputs
    ordered_images = sorted(
        list(enumerate(image_elements)),
        key=lambda it: (it[1].get("layer", 0), it[0]),
    )
    image_inputs: list[Path] = []
    image_input_map: list[tuple[dict, int]] = []
    for _, element in ordered_images:
        media_path = Path(element["source_uri"])
        if not media_path.exists():
            if strict:
                raise FileNotFoundError(media_path)
            continue
        image_inputs.append(media_path)
        image_input_map.append((element, 1 + len(image_inputs) - 1))
        if element["type"] == "image":
            cmd += ["-loop", "1", "-t", str(duration), "-i", str(media_path)]
        elif element["type"] == "gif":
            cmd += ["-stream_loop", "-1", "-i", str(media_path)]
        else:
            cmd += ["-i", str(media_path)]

    # Audio inputs (music + sfx tracks)
    audio_input_map: list[tuple[dict, int]] = []
    next_input_idx = 1 + len(image_inputs)
    for element in audio_elements:
        source_uri = element.get("source_uri")
        audio_path = Path(source_uri) if source_uri else None
        if not audio_path or not audio_path.exists():
            semantic_key = (
                element.get("metadata", {}).get("sfx_key")
                if isinstance(element.get("metadata", {}), dict)
                else None
            )
            audio_path = resolve_semantic_sfx(semantic_key)
        if not audio_path or not audio_path.exists():
            if strict:
                raise FileNotFoundError(source_uri or "missing_sfx_source")
            continue
        cmd += ["-i", str(audio_path)]
        audio_input_map.append((element, next_input_idx))
        next_input_idx += 1

    # Build filter graph
    filters: list[str] = [_build_base_video_filter(payload)]
    base_label = "base0"
    # Visual overlays (image/gif/video)
    for element, input_index in image_input_map:
        actions = sorted(_resolve_semantic_actions(payload, actions_by_id.get(element["id"], [])), key=lambda a: a.get("t_start", 0.0))
        actions = _coarsen_actions(actions, max_actions=10 if element.get("type") == "video" else 14)
        x = element.get("transform", {}).get("x", 0)
        y = element.get("transform", {}).get("y", 0)
        prev_x = float(x)
        prev_y = float(y)

        for action in actions:
            if action.get("op") not in ("show", "transition_whip_blur_zoom"):
                continue
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            scale = float(params.get("scale", 1.0))
            action_x = float(params.get("x", prev_x))
            action_y = float(params.get("y", prev_y))
            motion_from_x = float(params.get("from_x", prev_x))
            motion_from_y = float(params.get("from_y", prev_y))
            action_x_expr, action_y_expr = _overlay_xy_motion(
                motion_from_x,
                motion_from_y,
                action_x,
                action_y,
                t_start,
                t_end,
                ease=str(params.get("motion_ease", "smooth")),
            )
            action_x_expr = _escape_filter_expr(action_x_expr)
            action_y_expr = _escape_filter_expr(action_y_expr)
            trim_in = float(params.get("trim_in", 0.0))
            trim_out = params.get("trim_out")
            round_corners = _to_int(params.get("round_corners", 0), 0)

            seg_dur = max(0.0, t_end - t_start)
            if trim_out is not None:
                seg_dur = min(seg_dur, max(0.0, float(trim_out) - trim_in))
            seg_dur = _normalized_duration(seg_dur)
            if seg_dur <= 0.0:
                continue
            crop_w = params.get("crop_w")
            crop_h = params.get("crop_h")
            crop_x = params.get("crop_x", 0)
            crop_y = params.get("crop_y", 0)
            chain = f"[{input_index}:v]trim=start={trim_in}:duration={seg_dur},setpts=PTS-STARTPTS"
            if crop_w is not None and crop_h is not None:
                try:
                    cw = float(crop_w)
                    ch = float(crop_h)
                    cx = float(crop_x)
                    cy = float(crop_y)
                    chain += f",crop=iw*{cw}:ih*{ch}:iw*{cx}:ih*{cy}"
                except (TypeError, ValueError):
                    pass
            chain += f",scale=iw*{scale}:ih*{scale}"
            if action.get("op") == "transition_whip_blur_zoom":
                chain += ",rotate=0.03,gblur=sigma=10,scale=iw*1.08:ih*1.08"
            fade_in_s = _safe_float(params.get("fade_in_s"))
            fade_out_s = _safe_float(params.get("fade_out_s"))
            if (fade_in_s and fade_in_s > 0.0) or (fade_out_s and fade_out_s > 0.0):
                chain += ",format=rgba"
                if fade_in_s and fade_in_s > 0.0:
                    chain += f",fade=t=in:st=0:d={min(fade_in_s, seg_dur/2):.3f}:alpha=1"
                if fade_out_s and fade_out_s > 0.0:
                    out_st = max(0.0, seg_dur - min(fade_out_s, seg_dur / 2))
                    chain += f",fade=t=out:st={out_st:.3f}:d={min(fade_out_s, seg_dur/2):.3f}:alpha=1"
            rounded = _rounded_corners_filter(round_corners)
            if rounded:
                chain += f",{rounded}"
            label = f"img_{element['id']}_{int(t_start*1000)}"
            filters.append(f"{chain}[{label}]")
            out_label = f"v{len(filters)}"
            filters.append(
                f"[{base_label}][{label}]overlay={action_x_expr}:{action_y_expr}:enable='between(t\\,{t_start}\\,{t_end})'[{out_label}]"
            )
            base_label = out_label
            prev_x = action_x
            prev_y = action_y

    # Caption drawtext
    video_meta = payload.get("video", {}).get("metadata", {})
    global_caption_offset = 0.0
    if isinstance(video_meta, dict):
        try:
            global_caption_offset = float(video_meta.get("caption_time_offset_s", 0.0))
        except (TypeError, ValueError):
            global_caption_offset = 0.0

    caption_jobs: list[dict] = []
    for element in caption_elements:
        actions = sorted(_resolve_semantic_actions(payload, actions_by_id.get(element["id"], [])), key=lambda a: a.get("t_start", 0.0))
        actions = _coarsen_actions(actions, max_actions=max(8, min(400, len(actions))))
        x = element.get("transform", {}).get("x", 0)
        y = element.get("transform", {}).get("y", 0)
        caption_defaults = {
            "font_size": element.get("font_size"),
            "font_weight": element.get("font_weight"),
            "font_style": "normal",
            "color": element.get("color"),
            "stroke_color": element.get("stroke_color"),
            "stroke_width": element.get("stroke_width"),
            "shadow": element.get("shadow"),
            "x": x,
            "y": y,
        }

        for action in actions:
            if action.get("op") != "show":
                continue
            params = dict(caption_defaults)
            params.update(action.get("params", {}))
            local_caption_offset = float(params.get("caption_time_offset_s", 0.0) or 0.0)
            t_start = float(action.get("t_start", 0.0)) + global_caption_offset + local_caption_offset
            t_end = float(action.get("t_end", 0.0)) + global_caption_offset + local_caption_offset
            if t_end <= t_start:
                continue
            text_raw = params.get("text", element.get("text", ""))
            if not str(text_raw).strip():
                continue
            caption_jobs.append(
                {
                    "element_id": element.get("id"),
                    "t_start": t_start,
                    "t_end": t_end,
                    "x": float(params.get("x", x)),
                    "y": float(params.get("y", y)),
                    "params": params,
                }
            )

    caption_jobs = _normalize_caption_jobs(caption_jobs)
    caption_jobs = _suppress_overlapping_caption_jobs(caption_jobs)
    for job in sorted(caption_jobs, key=lambda j: (j["t_start"], j["t_end"])):
        params = job["params"]
        t_start = float(job["t_start"])
        t_end = float(job["t_end"])
        text = _escape_text(str(params.get("text", "")))
        if not text:
            continue
        font_size = _to_int(params.get("font_size", 48), 48)
        font_weight = params.get("font_weight", "regular")
        font_style = params.get("font_style", "normal")
        color = _safe_drawtext_color(params.get("color", "#FFFFFF"), fallback="0xFFFFFF")
        stroke_color = _safe_drawtext_color(params.get("stroke_color", "#000000"), fallback="0x000000")
        stroke_width = _to_int(params.get("stroke_width", 0), 0)
        shadow = params.get("shadow")
        shadow_x = 0
        shadow_y = 0
        shadow_color = "0x000000"
        if isinstance(shadow, dict):
            shadow_x = _to_int(shadow.get("x", 0), 0)
            shadow_y = _to_int(shadow.get("y", 0), 0)
            shadow_color = _safe_drawtext_color(shadow.get("color", "#000000"), fallback="0x000000")
        x_local, y_local = _resolve_caption_position(
            params,
            width,
            height,
            float(job["x"]),
            float(job["y"]),
        )
        fontfile = _fontfile_for(font_style, font_weight, params.get("font_family"))
        font_part = f"fontfile='{fontfile}':" if fontfile else ""
        stroke_part = f":borderw={stroke_width}:bordercolor={stroke_color}" if stroke_width > 0 else ""
        shadow_part = (
            f":shadowx={shadow_x}:shadowy={shadow_y}:shadowcolor={shadow_color}"
            if (shadow_x != 0 or shadow_y != 0)
            else ""
        )
        box_part = ""
        bg_opacity = _safe_float(params.get("background_opacity"))
        if bg_opacity is not None and bg_opacity > 0:
            bg_opacity = max(0.0, min(1.0, bg_opacity))
            bg_color = _safe_drawtext_color(params.get("background_color", "#000000"), fallback="0x000000")
            box_border = _to_int(params.get("box_border", 14), 14)
            box_part = f":box=1:boxcolor={bg_color}@{bg_opacity}:boxborderw={box_border}"
        # Optional stacked words mode: render each word on a new line with staggered entrance.
        text_mode = str(params.get("text_mode", "") or "").strip().lower()
        if text_mode in {"stack_words", "word_stack"}:
            step = _to_int(params.get("stack_line_step", 86), 86)
            words = [w for w in str(params.get("text", "")).split(" ") if w.strip()]
            if words:
                # Keep stacked captions fully inside frame.
                max_start_y = (height - 80) - max(0, len(words) - 1) * step
                min_start_y = 80
                stack_base_y = max(min_start_y, min(max_start_y, y_local))
                st = float(params.get("stack_stagger_s", 0.06) or 0.06)
                hold = float(params.get("stack_hold_s", 0.22) or 0.22)
                for wi, wtxt in enumerate(words):
                    ws = max(t_start, t_start + wi * st)
                    we = min(t_end, ws + hold)
                    if we <= ws:
                        continue
                    w_fs = _clamp_caption_font_size(font_size, wtxt, width)
                    w_text = _escape_text(wtxt)
                    wx = f"{x_local}-text_w/2"
                    wy = f"{(stack_base_y + wi * step)}-text_h/2"
                    w_color = color
                    imp_words = params.get("important_words", []) or []
                    if isinstance(imp_words, list) and any(str(x).lower() == wtxt.lower().strip(".,!?") for x in imp_words):
                        w_color = _safe_drawtext_color(params.get("highlight_color", "#FFD84D"), fallback="0xFFD84D")
                        w_fs = _clamp_caption_font_size(int(w_fs * float(params.get("important_scale", 1.2) or 1.2)), wtxt, width)
                    draw_w = (
                        f"drawtext={font_part}text='{w_text}':"
                        f"x={wx}:y={wy}:fontcolor={w_color}:fontsize={w_fs}"
                        f"{stroke_part}{shadow_part}{box_part}:fix_bounds=1:"
                        f"enable='between(t\\,{ws}\\,{we})'"
                    )
                    out_label = f"v{len(filters)}"
                    filters.append(f"[{base_label}]{draw_w}[{out_label}]")
                    base_label = out_label
                continue

        x_local = _fit_caption_center_x(x_local, str(params.get("text", "")), font_size, width)
        x_expr_local = f"{x_local}-text_w/2"
        y_expr_local = f"{y_local}-text_h/2"
        if params.get("current_word_behavior") or params.get("word_live_pop"):
            # Avoid turning an entire multi-word phrase to highlight color.
            if params.get("color") in (None, "") and " " not in str(params.get("text", "")).strip():
                color = params.get("highlight_color", "#FFD84D")
            scale = float(params.get("current_word_scale", 1.28) or 1.28)
            font_size = int(max(font_size, int(font_size * scale)))
        important_scale = float(params.get("importance_boost", 1.0) or 1.0)
        if important_scale > 1.0:
            font_size = int(max(font_size, int(font_size * important_scale)))
        font_size = _clamp_caption_font_size(font_size, str(params.get("text", "")), width)
        caption_anim = str(
            params.get("caption_animation", params.get("animation", params.get("anim", ""))) or ""
        ).strip().lower()
        intro_dur = float(params.get("animation_duration", params.get("anim_in_duration", 0.20)) or 0.20)
        intro_dur = max(0.0, min(intro_dur, max(0.0, t_end - t_start)))

        if caption_anim and intro_dur > 0.02:
            x_anim, y_anim, a_anim = _caption_anim_exprs(
                caption_anim, x_local, y_local, t_start, t_end, intro_dur
            )
            # Intro phase (animated)
            intro_fs = font_size
            if caption_anim in {"pop", "pop_bounce", "bounce", "bounce_in"}:
                intro_fs = _clamp_caption_font_size(int(font_size * 1.18), str(params.get("text", "")), width)
            draw_intro = (
                f"drawtext={font_part}text='{text}':"
                f"x={x_anim}:y={y_anim}:fontcolor={color}:fontsize={intro_fs}:alpha='{a_anim}'"
                f"{stroke_part}{shadow_part}{box_part}:fix_bounds=1:"
                f"enable='between(t\\,{t_start}\\,{(t_start + intro_dur)})'"
            )
            out_intro = f"v{len(filters)}"
            filters.append(f"[{base_label}]{draw_intro}[{out_intro}]")
            base_label = out_intro
            # Hold phase (stable)
            hold_start = t_start + intro_dur
            if t_end > hold_start:
                draw_hold = (
                    f"drawtext={font_part}text='{text}':"
                    f"x={x_expr_local}:y={y_expr_local}:fontcolor={color}:fontsize={font_size}"
                    f"{stroke_part}{shadow_part}{box_part}:fix_bounds=1:"
                    f"enable='between(t\\,{hold_start}\\,{t_end})'"
                )
                out_hold = f"v{len(filters)}"
                filters.append(f"[{base_label}]{draw_hold}[{out_hold}]")
                base_label = out_hold
        else:
            draw = (
                f"drawtext={font_part}text='{text}':"
                f"x={x_expr_local}:y={y_expr_local}:fontcolor={color}:fontsize={font_size}"
                f"{stroke_part}{shadow_part}{box_part}:fix_bounds=1:"
                f"enable='between(t\\,{t_start}\\,{t_end})'"
            )
            out_label = f"v{len(filters)}"
            filters.append(f"[{base_label}]{draw}[{out_label}]")
            base_label = out_label

    # Audio chain (music + many sfx tracks with semantic moment support)
    out_audio_label = None
    if audio_input_map:
        audio_filters: list[str] = []
        seg_labels: list[str] = []
        seg_counter = 0
        global_audio_offset = 0.0
        if isinstance(video_meta, dict):
            try:
                global_audio_offset = float(video_meta.get("audio_time_offset_s", 0.0))
            except (TypeError, ValueError):
                global_audio_offset = 0.0

        for audio_element, audio_input_index in audio_input_map:
            actions = sorted(
                _resolve_semantic_actions(payload, actions_by_id.get(audio_element["id"], [])),
                key=lambda a: a.get("t_start", 0.0),
            )
            actions = _coarsen_actions(actions, max_actions=12)
            volume = audio_element.get("volume", 1.0)
            has_play_action = any(a.get("op") in ("play", "show") for a in actions)
            if not has_play_action:
                actions = [{"t_start": 0.0, "t_end": duration, "op": "play", "params": {}}]

            for action in actions:
                if action.get("op") not in ("play", "show"):
                    continue
                params = action.get("params", {})
                local_audio_offset = float(params.get("audio_time_offset_s", 0.0) or 0.0)
                t_start = float(action.get("t_start", 0.0)) + global_audio_offset + local_audio_offset
                t_end = float(action.get("t_end", 0.0)) + global_audio_offset + local_audio_offset
                if t_end <= t_start:
                    continue
                # semantic sfx via params/moment without explicit file input
                semantic_key = params.get("sfx_key")
                if semantic_key and not audio_element.get("source_uri"):
                    resolved = resolve_semantic_sfx(str(semantic_key))
                    if resolved is None:
                        continue
                trim_in = float(params.get("trim_in", 0.0))
                trim_out = params.get("trim_out")
                seg_dur = max(0.0, t_end - t_start)
                if trim_out is not None:
                    seg_dur = min(seg_dur, max(0.0, float(trim_out) - trim_in))
                seg_dur = _normalized_duration(seg_dur)
                if seg_dur <= 0.0:
                    continue
                seg_label = f"a{seg_counter}"
                seg_counter += 1
                delay_ms = int(t_start * 1000)
                trim_clause = f"atrim=start={trim_in}:duration={seg_dur}"
                audio_filters.append(
                    f"[{audio_input_index}:a]{trim_clause},asetpts=PTS-STARTPTS,"
                    f"volume={params.get('volume', volume)},adelay={delay_ms}|{delay_ms}[{seg_label}]"
                )
                seg_labels.append(f"[{seg_label}]")

        if seg_labels:
            if len(seg_labels) > 1:
                audio_filters.append(f"{''.join(seg_labels)}amix=inputs={len(seg_labels)}[a]")
                out_audio_label = "[a]"
            else:
                out_audio_label = seg_labels[0]
            filters.extend(audio_filters)

    filter_graph = ";".join(filters)
    cmd_suffix = [
        "-map",
        f"[{base_label}]",
    ]
    if out_audio_label is not None:
        cmd_suffix += ["-map", out_audio_label]
    cmd_suffix += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]

    _run_ffmpeg_with_filter(cmd, filter_graph, cmd_suffix)
    return output_path


def _render_audio(payload: dict, output_path: Path, audio_path: Path, element: dict, actions: list[dict]) -> None:
    width, height = _video_size(payload)
    fps = _video_fps(payload)
    bg_color = _video_bg(payload)
    duration = float(element["timing"]["duration"])
    volume = element.get("volume", 1.0)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
        "-i",
        str(audio_path),
        "-filter_complex",
    ]

    # Build audio timeline from actions.
    audio_filters: list[str] = []
    seg_labels: list[str] = []
    resolved_actions = _resolve_semantic_actions(payload, actions)
    for idx, action in enumerate(resolved_actions):
        if action.get("op") not in ("play", "show"):
            continue
        t_start = float(action.get("t_start", 0.0))
        t_end = float(action.get("t_end", 0.0))
        params = action.get("params", {})
        trim_in = float(params.get("trim_in", 0.0))
        trim_out = params.get("trim_out")
        length = element.get("length")
        if length is not None:
            trim_out = min(float(trim_out) if trim_out is not None else float(length), float(length))
        seg_dur = max(0.0, t_end - t_start)
        if trim_out is not None:
            seg_dur = min(seg_dur, max(0.0, float(trim_out) - trim_in))
        seg_dur = _normalized_duration(seg_dur)
        if seg_dur <= 0.0:
            continue
        seg_label = f"a{idx}"
        delay_ms = int(t_start * 1000)
        trim_clause = f"atrim=start={trim_in}:duration={seg_dur}"
        audio_filters.append(
            f"[1:a]{trim_clause},asetpts=PTS-STARTPTS,volume={params.get('volume', volume)},"
            f"adelay={delay_ms}|{delay_ms}[{seg_label}]"
        )
        seg_labels.append(f"[{seg_label}]")

    if not seg_labels:
        # fallback: use loudest segment or start
        start_offset = 0.0
        if element.get("metadata", {}).get("crop_loudest"):
            start_offset = _find_loudest_segment(audio_path, duration)
        audio_filters.append(
            f"[1:a]atrim=start={start_offset}:duration={duration},asetpts=PTS-STARTPTS,volume={volume}[a]"
        )
        seg_labels = ["[a]"]

    if len(seg_labels) > 1:
        audio_filters.append(f"{''.join(seg_labels)}amix=inputs={len(seg_labels)}[aout]")
        out_label = "[aout]"
    else:
        out_label = seg_labels[0]

    cmd += [
        ";".join(audio_filters),
        "-map",
        "0:v",
        "-map",
        out_label,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def _resolve_elements_props_for_render(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve element properties from unified payload, refiner payload, or legacy properties_path."""
    inline_props: list[dict[str, Any]] = []
    for item in payload.get("elements", []):
        if not isinstance(item, dict):
            continue
        props = item.get("properties")
        if isinstance(props, dict) and props.get("type"):
            normalized = dict(props)
            if not normalized.get("id") and isinstance(item.get("element_id"), str):
                normalized["id"] = item["element_id"]
            inline_props.append(normalized)
    if inline_props:
        return inline_props

    updated = payload.get("updated_element_props", [])
    out_from_updated: list[dict[str, Any]] = []
    if isinstance(updated, list):
        for item in updated:
            if not isinstance(item, dict):
                continue
            props = item.get("properties", {})
            if isinstance(props, dict) and props.get("type"):
                normalized = dict(props)
                if not normalized.get("id") and isinstance(item.get("element_id"), str):
                    normalized["id"] = item["element_id"]
                out_from_updated.append(normalized)
    if out_from_updated:
        return out_from_updated

    properties_path = payload.get("properties_path")
    if properties_path:
        with open(properties_path, "r", encoding="utf-8") as handle:
            props_payload = json.load(handle)
        elements_props = props_payload.get("elements", [])
        out_legacy: list[dict[str, Any]] = []
        for item in elements_props:
            if not isinstance(item, dict):
                continue
            props = item.get("properties")
            if not isinstance(props, dict) or not props.get("type"):
                continue
            normalized = dict(props)
            if not normalized.get("id") and isinstance(item.get("element_id"), str):
                normalized["id"] = item["element_id"]
            out_legacy.append(normalized)
        return out_legacy

    raise ValueError(
        "No renderable element properties found. Provide inline `properties`, "
        "`updated_element_props`, or legacy `properties_path`."
    )


def render_from_json(input_path: str, *, strict: bool = False) -> Path:
    path = Path(input_path)
    print(f"[RENDER] Loading plan: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["_input_path"] = str(path)

    output_path = Path(payload["video"]["output_path"])
    _ensure_output_dir(output_path)
    print(f"[RENDER] Output: {output_path}")

    actions_by_id = {entry["element_id"]: entry.get("actions", []) for entry in payload["elements"]}
    elements_list = _resolve_elements_props_for_render(payload)
    print(f"[RENDER] Elements: {len(elements_list)} | Action tracks: {len(actions_by_id)}")

    if len(elements_list) > 1:
        print("[RENDER] Multi-element render path")
        return _render_multi_elements(payload, output_path, elements_list, actions_by_id, strict=strict)

    element = elements_list[0]
    actions = actions_by_id[element["id"]]
    element_type = element["type"]

    if element_type == "caption":
        print("[RENDER] Single element type: caption")
        _render_caption_words(payload, output_path, element, actions)
        return output_path

    if element_type == "image":
        print("[RENDER] Single element type: image")
        img = Image(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            transform=element.get("transform", {}),
        )
        _write_output_json(path, {"element": img.model_dump()})
        media_path = Path(img.source_uri)
        if media_path.exists():
            if not _render_image_actions(payload, output_path, media_path, actions, element):
                _render_overlay_media(payload, output_path, media_path, element, is_image=True)
        elif strict:
            raise FileNotFoundError(media_path)
        return output_path

    if element_type == "gif":
        print("[RENDER] Single element type: gif")
        gif = GIF(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            loop=element.get("loop", True),
            transform=element.get("transform", {}),
        )
        _write_output_json(path, {"element": gif.model_dump()})
        media_path = Path(gif.source_uri)
        if media_path.exists():
            _render_overlay_media(payload, output_path, media_path, element, actions=actions)
        elif strict:
            raise FileNotFoundError(media_path)
        return output_path

    if element_type == "video":
        print("[RENDER] Single element type: video")
        video = Video(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            trim_in=element.get("trim_in", 0.0),
            trim_out=element.get("trim_out"),
            has_audio=element.get("has_audio", True),
            transform=element.get("transform", {}),
        )
        _write_output_json(path, {"element": video.model_dump()})
        media_path = Path(video.source_uri)
        if media_path.exists():
            _render_overlay_media(payload, output_path, media_path, element, actions=actions)
        elif strict:
            raise FileNotFoundError(media_path)
        return output_path

    if element_type == "figure":
        print("[RENDER] Single element type: figure")
        figure = Figure(
            id=element["id"],
            timing=Timing(**element["timing"]),
            figure_type=element.get("figure_type", "shape"),
            payload_uri=element.get("payload_uri"),
            transform=element.get("transform", {}),
        )
        _write_output_json(path, {"element": figure.model_dump()})
        if figure.payload_uri:
            media_path = Path(figure.payload_uri)
            if media_path.exists():
                _render_overlay_media(payload, output_path, media_path, element)
            elif strict:
                raise FileNotFoundError(media_path)
        return output_path

    if element_type == "music":
        print("[RENDER] Single element type: music")
        music = Music(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            loop=element.get("loop", True),
            volume=element.get("volume", 1.0),
        )
        _write_output_json(path, {"element": music.model_dump()})
        media_path = Path(music.source_uri)
        if media_path.exists():
            _render_audio(payload, output_path, media_path, element, actions)
        elif strict:
            raise FileNotFoundError(media_path)
        return output_path

    if element_type == "sfx":
        print("[RENDER] Single element type: sfx")
        sfx = Sfx(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            volume=element.get("volume", 1.0),
        )
        _write_output_json(path, {"element": sfx.model_dump()})
        media_path = Path(sfx.source_uri)
        if media_path.exists():
            _render_audio(payload, output_path, media_path, element, actions)
        elif strict:
            raise FileNotFoundError(media_path)
        return output_path

    raise ValueError(f"Unknown element type: {element_type}")


def main() -> None:
    import argparse
    from vasp.core.serialization import serialize_unified_element_json

    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", help="Path to the input JSON.")
    parser.add_argument("--strict", action="store_true", help="Fail if media is missing.")
    parser.add_argument(
        "--serialize-only",
        action="store_true",
        help="Only generate element.json.",
    )
    args = parser.parse_args()
    input_path = Path(args.input_json)
    with open(input_path, "r", encoding="utf-8") as handle:
        raw_payload = json.load(handle)

    # Support direct rendering from already-serialized actions/inter JSON.
    # This avoids re-serializing plans where elements use `element_id` (not `id`).
    if _is_actions_or_inter_payload(raw_payload):
        if args.serialize_only:
            print("[RENDER] Input is already actions/inter JSON. Skipping serialization.")
            return
        render_from_json(str(input_path), strict=args.strict)
        return

    element_json = serialize_unified_element_json(args.input_json, drop_nulls=True)
    actions_path = input_path.with_name("element.json")
    with open(actions_path, "w", encoding="utf-8") as handle:
        json.dump(element_json, handle, indent=2)

    if not args.serialize_only:
        render_from_json(str(actions_path), strict=args.strict)


def _is_actions_or_inter_payload(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if "video" not in payload or "elements" not in payload:
        return False
    elements = payload.get("elements", [])
    if not isinstance(elements, list):
        return False
    if not elements:
        return True
    sample = elements[0]
    if not isinstance(sample, dict):
        return False
    if "element_id" not in sample or "actions" not in sample:
        return False
    has_inline_props = any(isinstance(e, dict) and isinstance(e.get("properties"), dict) for e in elements)
    has_updated = isinstance(payload.get("updated_element_props"), list)
    has_legacy = "properties_path" in payload
    return has_inline_props or has_updated or has_legacy


if __name__ == "__main__":
    main()
