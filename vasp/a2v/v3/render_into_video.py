from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

LARGE_RENDER_DURATION_THRESHOLD = 45.0
LARGE_RENDER_BACKGROUND_THRESHOLD = 25
LARGE_RENDER_CAPTION_THRESHOLD = 40
LARGE_RENDER_CHUNK_SECONDS = 12.0


def _run_ffmpeg_quiet(cmd: list[str]) -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise subprocess.CalledProcessError(
            124,
            cmd,
            output=exc.stdout,
            stderr=(exc.stderr or "") + "\nFFmpeg timed out; falling back to safe render.",
        ) from exc
    if result.returncode == 0:
        return
    stderr_tail = (result.stderr or result.stdout or "").strip()[-5000:]
    if stderr_tail:
        print(stderr_tail)
    raise subprocess.CalledProcessError(
        result.returncode,
        cmd,
        output=result.stdout,
        stderr=result.stderr,
    )


def _stderr_text(exc: subprocess.CalledProcessError) -> str:
    return str((exc.stderr or exc.output or "") or "")


def _is_oom_error(exc: subprocess.CalledProcessError) -> bool:
    text = _stderr_text(exc).lower()
    return "cannot allocate memory" in text or "failed to inject frame" in text or "error while filtering" in text


def _safe_fallback_render(
    *,
    out: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
    audio_src: Path | None,
    reason: str,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    report_path = out.with_suffix(".fallback_render.txt")
    report_path.write_text(reason, encoding="utf-8")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=#000000:s={width}x{height}:d={duration}:r={fps}",
    ]
    if audio_src and audio_src.exists():
        cmd += ["-i", str(audio_src)]
        suffix = [
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ]
    else:
        suffix = [
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
    _run_ffmpeg_quiet(cmd + suffix)


def _f(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _hex(s: Any, fallback: str = "0x000000") -> str:
    v = str(s or "").strip()
    if v.startswith("#") and len(v) in (7, 9):
        return "0x" + v[1:7]
    if v.startswith("0x"):
        return v
    return fallback


def _rgba_box(v: Any) -> tuple[str, float]:
    s = str(v or "").strip()
    if s.startswith("rgba(") and s.endswith(")"):
        parts = [p.strip() for p in s[5:-1].split(",")]
        if len(parts) == 4:
            try:
                r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
                a = max(0.0, min(1.0, float(parts[3])))
                return f"0x{r:02X}{g:02X}{b:02X}", a
            except Exception:
                pass
    return _hex(s), 0.45


def _caption_box_filter(style: dict[str, Any]) -> str:
    bg_raw = str(style.get("background_color") or "").strip()
    if bg_raw.lower() in {"", "none", "transparent"}:
        return ""
    box_color, box_alpha = _rgba_box(bg_raw)
    if "background_opacity" in style:
        box_alpha = max(0.0, min(1.0, _f(style.get("background_opacity"), box_alpha)))
    if box_alpha <= 0.01:
        return ""
    return f":box=1:boxcolor={box_color}@{box_alpha}:boxborderw=14"


def _background_filter(row: dict[str, Any], width: int, height: int, duration: float, fps: int, opacity: float, label: str) -> str:
    bg_type = str(row.get("type") or "solid").lower()
    color = _hex(row.get("color"), "0x000000")
    secondary = _hex(row.get("secondary_color"), color)
    grain = max(0.0, min(0.35, _f(row.get("grain"), 0.0)))
    vignette = max(0.0, min(0.85, _f(row.get("vignette"), 0.0)))
    blur_strength = max(0.0, min(0.45, _f(row.get("blur_strength"), _f(row.get("blur"), 0.0))))
    glow = max(0.0, min(0.4, _f(row.get("glow"), 0.0)))
    chain = f"color=c={color}:s={width}x{height}:d={duration}:r={fps},format=rgba"
    if bg_type == "gradient":
        # Lightweight, renderer-safe gradient approximation: layered color bands.
        chain += (
            f",drawbox=x=0:y=0:w=iw:h=ih/3:color={secondary}@0.26:t=fill"
            f",drawbox=x=0:y=ih*2/3:w=iw:h=ih/3:color={secondary}@0.20:t=fill"
            f",drawbox=x=iw*0.08:y=ih*0.42:w=iw*0.84:h=ih*0.16:color={secondary}@0.13:t=fill"
        )
    elif bg_type == "vignette":
        chain += (
            f",drawbox=x=iw*0.18:y=ih*0.18:w=iw*0.64:h=ih*0.64:color={secondary}@0.16:t=fill"
            f",drawbox=x=0:y=0:w=iw:h=ih/6:color={secondary}@0.24:t=fill"
            f",drawbox=x=0:y=ih*5/6:w=iw:h=ih/6:color={secondary}@0.28:t=fill"
            f",drawbox=x=0:y=0:w=iw/12:h=ih:color={secondary}@0.18:t=fill"
            f",drawbox=x=iw*11/12:y=0:w=iw/12:h=ih:color={secondary}@0.18:t=fill"
        )
        if "violet" in str(row.get("reason") or "").lower() or secondary == "0x6D28D9":
            chain += (
                f",drawbox=x=0:y=ih*0.30:w=iw:h=ih*0.40:color={secondary}@0.18:t=fill"
                f",drawbox=x=iw*0.08:y=ih*0.12:w=iw*0.84:h=10:color={secondary}@0.42:t=fill"
                f",drawbox=x=iw*0.08:y=ih*0.88:w=iw*0.84:h=10:color={secondary}@0.36:t=fill"
            )
    elif bg_type == "pattern":
        chain += (
            f",drawbox=x=0:y=ih*0.18:w=iw:h=12:color={secondary}@0.35:t=fill"
            f",drawbox=x=0:y=ih*0.50:w=iw:h=10:color={secondary}@0.22:t=fill"
            f",drawbox=x=0:y=ih*0.82:w=iw:h=12:color={secondary}@0.30:t=fill"
            f",drawbox=x=iw*0.10:y=ih*0.28:w=iw*0.80:h=2:color=white@0.14:t=fill"
            f",drawbox=x=iw*0.16:y=ih*0.62:w=iw*0.68:h=2:color=white@0.10:t=fill"
        )
    elif bg_type == "blur":
        radius = max(4, int(blur_strength * 56)) if blur_strength > 0 else 12
        chain += (
            f",drawbox=x=0:y=0:w=iw:h=ih:color={secondary}@0.18:t=fill"
            f",boxblur=luma_radius={radius}:luma_power=1:chroma_radius={max(4, radius // 2)}:chroma_power=1"
        )
    if glow > 0:
        chain += (
            f",drawbox=x=iw*0.10:y=ih*0.22:w=iw*0.80:h=ih*0.18:color={secondary}@{min(0.32, glow)}:t=fill"
            f",drawbox=x=iw*0.22:y=ih*0.58:w=iw*0.56:h=ih*0.13:color={secondary}@{min(0.24, glow * 0.75)}:t=fill"
        )
    if bg_type == "vignette" or vignette > 0:
        strength = max(vignette, 0.22)
        chain += (
            f",drawbox=x=0:y=0:w=iw:h=ih/7:color=black@{min(0.55, strength)}:t=fill"
            f",drawbox=x=0:y=ih*6/7:w=iw:h=ih/7:color=black@{min(0.65, strength + 0.08)}:t=fill"
            f",drawbox=x=0:y=0:w=iw/14:h=ih:color=black@{min(0.42, strength * 0.7)}:t=fill"
            f",drawbox=x=iw*13/14:y=0:w=iw/14:h=ih:color=black@{min(0.42, strength * 0.7)}:t=fill"
        )
    if "letterbox" in str(row.get("reason") or "").lower() or str(row.get("notes") or "").lower().find("film") >= 0:
        chain += ",drawbox=x=0:y=0:w=iw:h=90:color=black@0.56:t=fill,drawbox=x=0:y=ih-90:w=iw:h=90:color=black@0.56:t=fill"
    if grain > 0:
        # Deterministic pseudo-grain: low-opacity sparse dark scan lines. It is
        # intentionally subtle so it cannot distract from captions.
        alpha = min(0.16, grain)
        chain += (
            f",drawbox=x=0:y=ih*0.23:w=iw:h=2:color=white@{alpha}:t=fill"
            f",drawbox=x=0:y=ih*0.47:w=iw:h=1:color=black@{alpha}:t=fill"
            f",drawbox=x=0:y=ih*0.71:w=iw:h=2:color=white@{alpha * 0.7}:t=fill"
        )
    chain += f",colorchannelmixer=aa={opacity}[{label}]"
    return chain


def _fontfile() -> str:
    for p in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/calibri.ttf"):
        if Path(p).exists():
            return p.replace("\\", "/").replace(":", r"\:")
    return ""


def _escape_text(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("'", "")
        .replace("\n", " ")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("%", r"\%")
    )


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", str(text).strip()) if w]


def _caption_y_expr(anim_type: str, base_y: str, ts: float) -> str:
    if anim_type == "slide_up":
        return f"{base_y}+42*(1-min(max((t-{ts})/0.35\\,0)\\,1))"
    if anim_type in {"pop", "bounce"}:
        return f"{base_y}-18*sin(min(max((t-{ts})/0.28\\,0)\\,1)*PI)"
    if anim_type == "stomp":
        return f"{base_y}+24*(1-min(max((t-{ts})/0.12\\,0)\\,1))-10*sin(min(max((t-{ts})/0.18\\,0)\\,1)*PI)"
    if anim_type == "float":
        return f"{base_y}+8*sin(2*PI*(t-{ts}))"
    if anim_type == "typewriter":
        return f"{base_y}+4*sin(2*PI*min(max((t-{ts})/0.55\\,0)\\,1))"
    if anim_type == "wave_reveal":
        return f"{base_y}+6*sin(2*PI*(t-{ts})/0.8)"
    if anim_type == "glow_pulse":
        return f"{base_y}+3*sin(2*PI*(t-{ts})/1.2)"
    if anim_type == "blur_in":
        return f"{base_y}+20*(1-min(max((t-{ts})/0.24\\,0)\\,1))"
    return base_y


def _caption_alpha_expr(anim_type: str, ts: float, extra_delay: float = 0.0) -> str:
    start = ts + extra_delay
    if anim_type in {"typewriter", "word_reveal", "wave_reveal"}:
        return f":alpha='min(max((t-{start})/0.12\\,0)\\,1)'"
    if anim_type in {"fade", "blur_in"}:
        return f":alpha='min(max((t-{ts})/0.25\\,0)\\,1)'"
    if anim_type in {"pop", "bounce", "stomp"}:
        return f":alpha='min(max((t-{ts})/0.08\\,0)\\,1)'"
    if anim_type == "glow_pulse":
        return f":alpha='min(max((t-{ts})/0.14\\,0)\\,1)'"
    return ""


def _drawtext_filter(
    *,
    font_part: str,
    text: str,
    x_expr: str,
    y_expr: str,
    color: str,
    fontsize: int,
    box_part: str,
    alpha_part: str,
    ts: float,
    te: float,
) -> str:
    return (
        f"drawtext={font_part}text='{_escape_text(text)}':x={x_expr}:y={y_expr}:"
        f"fontcolor={color}:fontsize={fontsize}:borderw=3:bordercolor=0x000000"
        f"{box_part}{alpha_part}:fix_bounds=1:"
        f"enable='between(t\\,{ts}\\,{te})'"
    )


def _append_caption_filters(
    filters: list[str],
    base: str,
    index: int,
    *,
    text: str,
    ts: float,
    te: float,
    x: float,
    y: float,
    w: float,
    h: float,
    style: dict[str, Any],
    animation: dict[str, Any],
    font_part: str,
) -> str:
    fontsize = max(36, int(_f(style.get("font_size"), 64)))
    text_color = _hex(style.get("text_color"), "0xFFFFFF")
    highlight_color = _hex(style.get("highlight_color"), text_color)
    box_part = _caption_box_filter(style)
    anim_type = str(animation.get("type") or "").lower()
    intensity = str(animation.get("intensity") or "medium").lower()
    base_y = f"{y}+({h}-text_h)/2"
    y_expr = _caption_y_expr(anim_type, base_y, ts)
    cue_duration = max(0.1, te - ts)

    if anim_type == "typewriter":
        clean_text = str(text).strip()
        if clean_text:
            max_steps = 42 if intensity == "high" else 34
            reveal_span = min(cue_duration * 0.78, max(0.45, len(clean_text) * 0.035))
            step_count = max(1, min(len(clean_text), max_steps))
            for ci in range(step_count):
                end_char = max(1, round((ci + 1) * len(clean_text) / step_count))
                prefix = clean_text[:end_char]
                if ci < step_count - 1:
                    prefix += "|"
                step_start = ts + (ci * reveal_span / step_count)
                step_end = ts + ((ci + 1) * reveal_span / step_count) if ci < step_count - 1 else te
                draw = _drawtext_filter(
                    font_part=font_part,
                    text=prefix,
                    x_expr=f"{x}+({w}-text_w)/2",
                    y_expr=y_expr,
                    color=text_color,
                    fontsize=fontsize,
                    box_part=box_part if ci == 0 else "",
                    alpha_part=_caption_alpha_expr(anim_type, ts),
                    ts=step_start,
                    te=step_end,
                )
                out_label = f"v_cap{index}_type{ci}"
                filters.append(f"[{base}]{draw}[{out_label}]")
                base = out_label
            return base

    if anim_type == "wave_reveal":
        words = _words(text)
        if words:
            total_chars = sum(len(word) for word in words) + max(0, len(words) - 1)
            avg_char = fontsize * 0.55
            total_w = min(w, max(fontsize, total_chars * avg_char))
            start_x = x + max(0.0, (w - total_w) / 2.0)
            reveal_span = min(cue_duration * 0.72, max(0.36, len(words) * 0.16))
            if intensity == "high":
                reveal_span = min(cue_duration * 0.82, max(0.45, len(words) * 0.20))
            step = reveal_span / max(1, len(words))
            offset = 0.0
            for wi, word in enumerate(words):
                word_w = max(fontsize * 0.45, len(word) * avg_char)
                word_x = start_x + offset
                color = highlight_color if anim_type in {"word_reveal", "wave_reveal"} and wi % 3 == 1 else text_color
                word_y = y_expr
                if anim_type == "wave_reveal":
                    word_y = f"{y_expr}+{8 + (3 if intensity == 'high' else 0)}*sin(2*PI*(t-{ts + wi * step})/0.45)"
                draw = _drawtext_filter(
                    font_part=font_part,
                    text=word,
                    x_expr=f"{word_x}",
                    y_expr=word_y,
                    color=color,
                    fontsize=fontsize,
                    box_part="" if wi else box_part,
                    alpha_part=_caption_alpha_expr(anim_type, ts, wi * step),
                    ts=ts + wi * step,
                    te=te,
                )
                out_label = f"v_cap{index}_{wi}"
                filters.append(f"[{base}]{draw}[{out_label}]")
                base = out_label
                offset += word_w + fontsize * 0.38
            return base

    if anim_type == "glow_pulse":
        glow_label = f"v_cap{index}_glow"
        glow_alpha = f":alpha='0.22+0.18*sin(2*PI*(t-{ts})/0.7)'"
        glow_draw = _drawtext_filter(
            font_part=font_part,
            text=text,
            x_expr=f"{x}+({w}-text_w)/2",
            y_expr=y_expr,
            color=highlight_color,
            fontsize=fontsize + 4,
            box_part="",
            alpha_part=glow_alpha,
            ts=ts,
            te=te,
        )
        filters.append(f"[{base}]{glow_draw}[{glow_label}]")
        base = glow_label

    if anim_type == "blur_in":
        ghost_label = f"v_cap{index}_ghost"
        ghost_draw = _drawtext_filter(
            font_part=font_part,
            text=text,
            x_expr=f"{x}+({w}-text_w)/2",
            y_expr=f"{y_expr}+2",
            color=highlight_color,
            fontsize=fontsize + 2,
            box_part="",
            alpha_part=f":alpha='0.28*(1-min(max((t-{ts})/0.22\\,0)\\,1))'",
            ts=ts,
            te=min(te, ts + 0.45),
        )
        filters.append(f"[{base}]{ghost_draw}[{ghost_label}]")
        base = ghost_label

    draw = _drawtext_filter(
        font_part=font_part,
        text=text,
        x_expr=f"{x}+({w}-text_w)/2",
        y_expr=y_expr,
        color=text_color,
        fontsize=fontsize,
        box_part=box_part,
        alpha_part=_caption_alpha_expr(anim_type, ts),
        ts=ts,
        te=te,
    )
    out_label = f"v_cap{index}"
    filters.append(f"[{base}]{draw}[{out_label}]")
    return out_label


def _media_kind(path: str, declared: str = "") -> str:
    ext = Path(path).suffix.lower()
    if ext in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}:
        return "audio"
    if ext == ".gif":
        return "gif"
    if ext in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
        return "video"
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return "image"
    d = declared.lower()
    if "gif" in d or "sticker" in d:
        return "gif"
    if "video" in d:
        return "video"
    return "image"


def _background_merge_key(row: dict[str, Any]) -> tuple[Any, ...]:
    src = str(row.get("source_path") or row.get("path") or "").replace("\\", "/")
    if src:
        return ("image_source", src, round(_f(row.get("opacity"), 1.0), 3))
    return (
        src,
        str(row.get("type") or "solid").lower(),
        str(row.get("color") or ""),
        str(row.get("secondary_color") or ""),
        round(_f(row.get("opacity"), 1.0), 3),
        round(_f(row.get("grain"), 0.0), 3),
        round(_f(row.get("vignette"), 0.0), 3),
        round(_f(row.get("blur_strength"), _f(row.get("blur"), 0.0)), 3),
        round(_f(row.get("glow"), 0.0), 3),
    )


def _merge_background_timeline(rows: list[Any], duration: float) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ts = max(0.0, min(duration, _f(row.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _f(row.get("t_end"), ts)))
        if te <= ts:
            continue
        item = dict(row)
        item["t_start"] = ts
        item["t_end"] = te
        clean.append(item)
    clean.sort(key=lambda r: (_f(r.get("t_start"), 0.0), _f(r.get("t_end"), 0.0)))

    merged: list[dict[str, Any]] = []
    for row in clean:
        if not merged:
            merged.append(row)
            continue
        prev = merged[-1]
        same_design = _background_merge_key(prev) == _background_merge_key(row)
        touches = _f(row.get("t_start"), 0.0) <= _f(prev.get("t_end"), 0.0) + 0.05
        if same_design and touches:
            prev["t_end"] = max(_f(prev.get("t_end"), 0.0), _f(row.get("t_end"), 0.0))
        else:
            merged.append(row)
    return merged


def _merge_background_events(events: list[Any]) -> list[dict[str, Any]]:
    clean = [dict(row) for row in events if isinstance(row, dict)]
    clean.sort(key=lambda r: (_f(r.get("t_start"), 0.0), _f(r.get("t_end"), 0.0)))
    merged: list[dict[str, Any]] = []
    for row in clean:
        ts = _f(row.get("t_start"), 0.0)
        te = _f(row.get("t_end"), ts)
        if te <= ts:
            continue
        row["t_start"] = ts
        row["t_end"] = te
        if not merged:
            merged.append(row)
            continue
        prev = merged[-1]
        prev_src = str(prev.get("source_path") or prev.get("path") or "")
        row_src = str(row.get("source_path") or row.get("path") or "")
        prev_preset = str(prev.get("background_image_preset") or "")
        row_preset = str(row.get("background_image_preset") or "")
        same_source_or_preset = (prev_src and prev_src == row_src) or (prev_preset and prev_preset == row_preset)
        same_type = str(prev.get("type") or "").lower() == str(row.get("type") or "").lower()
        same_fit = str(prev.get("fit") or "cover").lower() == str(row.get("fit") or "cover").lower()
        gap_ok = ts - _f(prev.get("t_end"), 0.0) <= 0.03
        if same_source_or_preset and same_type and same_fit and gap_ok:
            prev["t_end"] = max(_f(prev.get("t_end"), 0.0), te)
        else:
            merged.append(row)
    return merged


def _prepare_render_asset(src_path: str | Path, cache_dir: str | Path) -> Path:
    src = _resolve_media_source(Path(src_path))
    if src.suffix.lower() != ".webp":
        return src
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{src.stem}.png"
    if out.exists() and out.stat().st_size > 0:
        return out
    cmd = ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", str(out)]
    _run_ffmpeg_quiet(cmd)
    return out


def _sanitize_background_rows(rows: list[dict[str, Any]], warnings: list[str], creativity_level: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        src = str(item.get("source_path") or item.get("path") or "").strip()
        if src and creativity_level <= 2:
            # Background WebP/JPG streams have repeatedly caused FFmpeg memory
            # failures on Windows when reused in complex graphs. Preserve the
            # preset's colors/effects instead of feeding the image stream.
            item.pop("source_path", None)
            item.pop("path", None)
            if str(item.get("type") or "").lower() == "image":
                item["type"] = "gradient"
            item.setdefault("reason", "background_image_sanitized_to_synthetic")
            warnings.append(f"background_image_sanitized:{Path(src).name}")
        out.append(item)
    return out


def _probe_decodable(path: Path, kind: str) -> bool:
    if not path.exists() or path.stat().st_size <= 1024:
        return False
    selector = "v:0" if kind in {"image", "gif", "video"} else "a:0"
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        selector,
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
    except Exception:
        return False
    return result.returncode == 0 and bool((result.stdout or "").strip())


def _resolve_media_source(src: Path) -> Path:
    if src.exists():
        return src
    name = src.name
    candidates = [
        Path("assets/library") / name,
        Path("assets/crawled_data") / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return src


def _large_render_required(inter: dict[str, Any], duration: float) -> bool:
    bg_count = len(inter.get("background_timeline") if isinstance(inter.get("background_timeline"), list) else [])
    cap_count = len(inter.get("caption_timeline") if isinstance(inter.get("caption_timeline"), list) else [])
    return duration > LARGE_RENDER_DURATION_THRESHOLD or bg_count > LARGE_RENDER_BACKGROUND_THRESHOLD or cap_count > LARGE_RENDER_CAPTION_THRESHOLD


def _large_render_cmd_options() -> list[str]:
    return ["-filter_threads", "1", "-filter_complex_threads", "1", "-threads", "4"]


def _large_encode_options() -> list[str]:
    return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def _large_bg_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["blur_strength"] = 0
    out["blur"] = 0
    out["glow"] = 0
    out["grain"] = 0
    if "vignette" in out:
        out["vignette"] = min(_f(out.get("vignette"), 0.0), 0.25)
    return out


def _render_background_track(inter: dict[str, Any], output_bg_path: str | Path, cache_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    canvas = inter.get("canvas") or {}
    width = int(_f(canvas.get("width"), 1080))
    height = int(_f(canvas.get("height"), 1920))
    fps = int(_f(canvas.get("fps"), 30))
    duration = _f(canvas.get("duration"), 0.0)
    out = Path(output_bg_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    raw_events = inter.get("background_timeline") if isinstance(inter.get("background_timeline"), list) else []
    clamped_events: list[dict[str, Any]] = []
    webp_cached = 0
    for row in _merge_background_events(raw_events):
        item = _large_bg_row(row)
        item["t_start"] = max(0.0, min(duration, _f(item.get("t_start"), 0.0)))
        item["t_end"] = max(0.0, min(duration, _f(item.get("t_end"), item["t_start"])))
        if item["t_end"] <= item["t_start"]:
            continue
        src_text = str(item.get("source_path") or item.get("path") or "").strip()
        if src_text:
            prepared = _prepare_render_asset(src_text, cache)
            if Path(src_text).suffix.lower() == ".webp" and prepared.suffix.lower() == ".png":
                webp_cached += 1
            item["source_path"] = str(prepared)
        clamped_events.append(item)

    def render_solid_part(path: Path, dur: float, row: dict[str, Any] | None = None) -> None:
        if row:
            local = dict(row)
            local["t_start"] = 0.0
            local["t_end"] = dur
            label = "bg"
            graph = _background_filter(local, width, height, dur, fps, max(0.0, min(1.0, _f(local.get("opacity"), 1.0))), label)
            _run_ffmpeg_quiet(
                [
                    "ffmpeg",
                    "-y",
                    *_large_render_cmd_options(),
                    "-filter_complex",
                    graph,
                    "-map",
                    f"[{label}]",
                    *_large_encode_options(),
                    "-r",
                    str(fps),
                    str(path),
                ]
            )
            return
        _run_ffmpeg_quiet(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=#000000:s={width}x{height}:d={dur}:r={fps}",
                *_large_encode_options(),
                "-r",
                str(fps),
                "-an",
                str(path),
            ]
        )

    def render_image_part(path: Path, src: Path, dur: float, row: dict[str, Any]) -> None:
        fit = str(row.get("fit") or "cover").lower()
        if fit == "contain":
            vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p"
        else:
            vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p"
        _run_ffmpeg_quiet(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-t",
                f"{dur:.3f}",
                "-i",
                str(src),
                "-vf",
                vf,
                *_large_encode_options(),
                "-r",
                str(fps),
                "-an",
                str(path),
            ]
        )

    parts: list[Path] = []
    cursor = 0.0
    for idx, row in enumerate(clamped_events):
        ts = max(0.0, min(duration, _f(row.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _f(row.get("t_end"), ts)))
        if te <= ts:
            continue
        if ts > cursor + 0.001:
            gap = cache / f"bg_part_{len(parts):03d}_gap.mp4"
            render_solid_part(gap, ts - cursor)
            parts.append(gap)
            cursor = ts
        start = max(ts, cursor)
        dur = te - start
        if dur <= 0.001:
            continue
        part = cache / f"bg_part_{len(parts):03d}_{idx:03d}.mp4"
        src_text = str(row.get("source_path") or row.get("path") or "").strip()
        src = _resolve_media_source(Path(src_text)) if src_text else Path("")
        if src_text and src.exists() and _probe_decodable(src, "image"):
            render_image_part(part, src, dur, row)
        else:
            render_solid_part(part, dur, row)
        parts.append(part)
        cursor = te
    if cursor < duration - 0.001:
        tail = cache / f"bg_part_{len(parts):03d}_tail.mp4"
        render_solid_part(tail, duration - cursor)
        parts.append(tail)
    if not parts:
        part = cache / "bg_part_000_black.mp4"
        render_solid_part(part, duration)
        parts.append(part)
    concat_list = cache / "background_parts.txt"
    concat_list.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    _run_ffmpeg_quiet(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(out)])
    return out, {
        "background_events_before": len(raw_events),
        "background_events_after_merge": len(clamped_events),
        "webp_cached": webp_cached,
        "background_parts": len(parts),
        "background_video": str(out),
    }


def _overlaps(ts: float, te: float, start: float, end: float) -> bool:
    return ts < end and start < te


def _render_chunk_video(
    *,
    inter: dict[str, Any],
    bg_video_path: Path,
    chunk_path: Path,
    chunk_start: float,
    chunk_end: float,
    fps: int,
) -> dict[str, Any]:
    canvas = inter.get("canvas") or {}
    width = int(_f(canvas.get("width"), 1080))
    height = int(_f(canvas.get("height"), 1920))
    chunk_dur = max(0.01, chunk_end - chunk_start)
    cmd = ["ffmpeg", "-y", "-ss", f"{chunk_start:.3f}", "-t", f"{chunk_dur:.3f}", "-i", str(bg_video_path)]
    next_idx = 1
    base_visual = inter.get("base_visual") if isinstance(inter.get("base_visual"), dict) else {}
    base_visual_input: tuple[dict[str, Any], int, str] | None = None
    if base_visual:
        src = _resolve_media_source(Path(str(base_visual.get("source_path") or "")))
        kind = _media_kind(str(src), str(base_visual.get("type") or "video"))
        if src.exists() and kind in {"image", "gif", "video"} and _probe_decodable(src, kind):
            base_visual_input = (base_visual, next_idx, kind)
            next_idx += 1
            if kind == "image":
                cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(src)]
            else:
                cmd += ["-stream_loop", "-1", "-i", str(src)]

    visuals = [
        v for v in (inter.get("visual_timeline") if isinstance(inter.get("visual_timeline"), list) else [])
        if isinstance(v, dict) and _overlaps(_f(v.get("t_start"), 0.0), _f(v.get("t_end"), 0.0), chunk_start, chunk_end)
    ]
    captions = [
        c for c in (inter.get("caption_timeline") if isinstance(inter.get("caption_timeline"), list) else [])
        if isinstance(c, dict) and _overlaps(_f(c.get("t_start"), 0.0), _f(c.get("t_end"), 0.0), chunk_start, chunk_end)
    ]
    visual_inputs: list[tuple[dict[str, Any], int, str, Path]] = []
    input_by_source: dict[str, tuple[int, str]] = {}
    warnings: list[str] = []
    for v in visuals:
        src = _resolve_media_source(Path(str(v.get("source_path") or "")))
        kind = _media_kind(str(src), str(v.get("type") or ""))
        if not src.exists() or kind not in {"image", "gif", "video"} or not _probe_decodable(src, kind):
            warnings.append(f"skip_chunk_visual:{v.get('element_id')}:{src}")
            continue
        key = str(src.resolve())
        if key not in input_by_source:
            input_by_source[key] = (next_idx, kind)
            next_idx += 1
            if kind == "image":
                cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(src)]
            else:
                cmd += ["-stream_loop", "-1", "-i", str(src)]
        idx, kind = input_by_source[key]
        visual_inputs.append((v, idx, kind, src))

    filters = [f"[0:v]scale={width}:{height},setpts=PTS-STARTPTS[base0]"]
    base = "base0"
    if base_visual_input is not None:
        bv, input_idx, kind = base_visual_input
        layout = bv.get("layout") if isinstance(bv.get("layout"), dict) else {}
        x = _f(layout.get("x"), 0.0)
        y = _f(layout.get("y"), 544.0)
        w = max(1, int(_f(layout.get("width"), 1080)))
        h = max(1, int(_f(layout.get("height"), 800)))
        opacity = max(0.0, min(1.0, _f(layout.get("opacity"), 1.0)))
        fit = str(layout.get("fit") or "cover").lower()
        force = "increase" if fit == "cover" else "decrease"
        chain = f"[{input_idx}:v]"
        if kind == "gif":
            chain += f"fps={fps},trim=start={chunk_start}:duration={chunk_dur},setpts=N/({fps}*TB),format=rgba"
        else:
            chain += f"trim=start={chunk_start}:duration={chunk_dur},setpts=PTS-STARTPTS,format=rgba"
        chain += f",scale={w}:{h}:force_original_aspect_ratio={force}"
        if fit == "cover":
            chain += f",crop={w}:{h}"
        if opacity < 0.999:
            chain += f",colorchannelmixer=aa={opacity}"
        filters.append(f"{chain}[base_visual]")
        out_label = "v_base_visual"
        filters.append(f"[{base}][base_visual]overlay={x}+({w}-overlay_w)/2:{y}+({h}-overlay_h)/2[{out_label}]")
        base = out_label

    for i, (v, input_idx, kind, _src) in enumerate(visual_inputs):
        v_start = _f(v.get("t_start"), 0.0)
        v_end = _f(v.get("t_end"), v_start)
        local_start = max(0.0, v_start - chunk_start)
        local_end = min(chunk_dur, v_end - chunk_start)
        if local_end <= local_start:
            continue
        media_offset = max(0.0, chunk_start - v_start)
        seg_dur = local_end - local_start
        layout = v.get("layout") if isinstance(v.get("layout"), dict) else {}
        x = _f(layout.get("x"), 0.0)
        y = _f(layout.get("y"), 544.0)
        w = max(1, int(_f(layout.get("width"), 1080)))
        h = max(1, int(_f(layout.get("height"), 800)))
        opacity = max(0.0, min(1.0, _f(layout.get("opacity"), 1.0)))
        fit = str(layout.get("fit") or "contain").lower()
        force = "increase" if fit == "cover" else "decrease"
        chain = f"[{input_idx}:v]"
        if kind == "gif":
            chain += f"fps={fps},trim=start={media_offset}:duration={seg_dur},setpts=N/({fps}*TB)+{local_start}/TB,format=rgba"
        else:
            chain += f"trim=start={media_offset}:duration={seg_dur},setpts=PTS-STARTPTS+{local_start}/TB,format=rgba"
        chain += f",scale={w}:{h}:force_original_aspect_ratio={force}"
        if fit == "cover":
            chain += f",crop={w}:{h}"
        if opacity < 0.999:
            chain += f",colorchannelmixer=aa={opacity}"
        label = f"vis{i}"
        filters.append(f"{chain}[{label}]")
        out_label = f"v_vis{i}"
        filters.append(f"[{base}][{label}]overlay={x}+({w}-overlay_w)/2:{y}+({h}-overlay_h)/2:enable='between(t\\,{local_start}\\,{local_end})'[{out_label}]")
        base = out_label

    font = _fontfile()
    font_part = f"fontfile='{font}':" if font else ""
    caption_count = 0
    for i, c in enumerate(captions):
        ts = max(0.0, _f(c.get("t_start"), 0.0) - chunk_start)
        te = min(chunk_dur, _f(c.get("t_end"), 0.0) - chunk_start)
        text = str(c.get("text", "")).strip()
        if te <= ts or not text:
            continue
        layout = c.get("layout") if isinstance(c.get("layout"), dict) else {}
        style = c.get("style") if isinstance(c.get("style"), dict) else {}
        animation = c.get("animation") if isinstance(c.get("animation"), dict) else {}
        base = _append_caption_filters(
            filters,
            base,
            i,
            text=text,
            ts=ts,
            te=te,
            x=_f(layout.get("x"), 90.0),
            y=_f(layout.get("y"), 1450.0),
            w=_f(layout.get("width"), 900.0),
            h=_f(layout.get("height"), 300.0),
            style=style,
            animation=animation,
            font_part=font_part,
        )
        caption_count += 1

    graph = ";".join(filters)
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = ["-map", f"[{base}]", "-an", *_large_encode_options(), "-r", str(fps), str(chunk_path)]
    with tempfile.NamedTemporaryFile("w", suffix=".ffgraph", delete=False, encoding="utf-8") as f:
        f.write(graph)
        graph_path = f.name
    try:
        _run_ffmpeg_quiet(cmd + _large_render_cmd_options() + ["-filter_complex_script", graph_path] + suffix)
    finally:
        Path(graph_path).unlink(missing_ok=True)
    return {"chunk": str(chunk_path), "visuals": len(visual_inputs), "captions": caption_count, "warnings": warnings}


def _render_chunks(inter: dict[str, Any], bg_video_path: str | Path, output_video_path: str | Path, chunk_seconds: float = LARGE_RENDER_CHUNK_SECONDS) -> dict[str, Any]:
    canvas = inter.get("canvas") or {}
    fps = int(_f(canvas.get("fps"), 30))
    duration = _f(canvas.get("duration"), 0.0)
    out = Path(output_video_path)
    cache_dir = out.parent / "render_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []
    chunk_reports: list[dict[str, Any]] = []
    count = max(1, int(math.ceil(duration / chunk_seconds)))
    for i in range(count):
        start = i * chunk_seconds
        end = min(duration, start + chunk_seconds)
        chunk = cache_dir / f"chunk_{i:03d}.mp4"
        chunk_reports.append(_render_chunk_video(inter=inter, bg_video_path=Path(bg_video_path), chunk_path=chunk, chunk_start=start, chunk_end=end, fps=fps))
        chunks.append(chunk)
    concat_list = cache_dir / "chunks.txt"
    concat_list.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in chunks), encoding="utf-8")
    concat_video = cache_dir / "concat_video.mp4"
    _run_ffmpeg_quiet(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(concat_video)])
    audio = inter.get("audio") if isinstance(inter.get("audio"), dict) else {}
    audio_src = _resolve_media_source(Path(str(audio.get("source_path") or ""))) if audio.get("source_path") else None
    if audio_src and audio_src.exists():
        _run_ffmpeg_quiet(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(concat_video),
                "-i",
                str(audio_src),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out),
            ]
        )
    else:
        _run_ffmpeg_quiet(["ffmpeg", "-y", "-i", str(concat_video), "-c", "copy", "-movflags", "+faststart", str(out)])
    return {"chunk_count": count, "chunks": chunk_reports, "concat_video": str(concat_video)}


def _render_large_mode(inter: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
    out = Path(output_path)
    cache_dir = out.parent / "render_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bg_video, bg_report = _render_background_track(inter, cache_dir / "background_base.mp4", cache_dir)
    chunk_report = _render_chunks(inter, bg_video, out, LARGE_RENDER_CHUNK_SECONDS)
    report = {**bg_report, **chunk_report, "output_path": str(out)}
    (out.with_suffix(".large_render_report.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out.with_suffix(".render_report.json")).write_text(json.dumps({"large_render_mode": True, **report}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "[A2V_V3_RENDER] large-render mode: "
        f"duration={_f((inter.get('canvas') or {}).get('duration'), 0.0):.3f}s "
        f"backgrounds={bg_report['background_events_before']}->{bg_report['background_events_after_merge']} "
        f"webp_cached={bg_report['webp_cached']} chunks={chunk_report['chunk_count']} output={out}"
    )
    return report


def render_into_video(
    inter_json_path: str | Path,
    media_json_path: str | Path,
    output_path: str | Path = "insta_edit.mp4",
    *,
    strict: bool = False,
) -> Path:
    inter = json.loads(Path(inter_json_path).read_text(encoding="utf-8-sig"))
    canvas = inter.get("canvas") or {}
    width = int(_f(canvas.get("width"), 1080))
    height = int(_f(canvas.get("height"), 1920))
    fps = int(_f(canvas.get("fps"), 30))
    duration = _f(canvas.get("duration"), 0.0)
    if duration <= 0:
        raise ValueError("inter canvas duration must be > 0")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if _large_render_required(inter, duration):
        _render_large_mode(inter, out)
        return out

    bg = "#000000"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={bg}:s={width}x{height}:d={duration}:r={fps}"]
    next_input_idx = 1
    warnings: list[str] = []
    debug_report: dict[str, Any] = {
        "input_inter_json": str(inter_json_path),
        "output_path": str(out),
        "duration": duration,
        "visual_rows_in_inter": len(inter.get("visual_timeline") if isinstance(inter.get("visual_timeline"), list) else []),
        "caption_rows_in_inter": len(inter.get("caption_timeline") if isinstance(inter.get("caption_timeline"), list) else []),
        "background_rows_in_inter": len(inter.get("background_timeline") if isinstance(inter.get("background_timeline"), list) else []),
        "visual_inputs": [],
        "background_inputs": [],
        "caption_filters": 0,
        "warnings": warnings,
    }

    creativity_level = int(_f(inter.get("creativity_level"), 2))
    raw_background_rows = inter.get("background_timeline") if isinstance(inter.get("background_timeline"), list) else []
    background_rows = _sanitize_background_rows(_merge_background_timeline(raw_background_rows, duration), warnings, creativity_level)
    if creativity_level <= 2:
        if background_rows:
            warnings.append(f"background_timeline_simplified:count={len(background_rows)} creativity={creativity_level}")
        background_rows = []
    bg_inputs: dict[int, int] = {}
    bg_input_by_source: dict[str, int] = {}
    for bg_i, bgrow in enumerate(background_rows):
        if not isinstance(bgrow, dict):
            continue
        src_text = str(bgrow.get("source_path") or bgrow.get("path") or "").strip()
        if not src_text:
            continue
        src = _resolve_media_source(Path(src_text))
        if not src.exists():
            warnings_msg = f"missing_background:{src}"
            if strict:
                raise FileNotFoundError(warnings_msg)
            warnings.append(warnings_msg)
            continue
        if not _probe_decodable(src, "image"):
            warnings_msg = f"skip_undecodable_background:{src}"
            if strict:
                raise ValueError(warnings_msg)
            warnings.append(warnings_msg)
            continue
        src_key = str(src.resolve())
        if src_key in bg_input_by_source:
            input_idx = bg_input_by_source[src_key]
        else:
            input_idx = next_input_idx
            next_input_idx += 1
            cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(src)]
            bg_input_by_source[src_key] = input_idx
        bg_inputs[bg_i] = input_idx
        debug_report["background_inputs"].append(
            {
                "source_path": src_text,
                "resolved_path": str(src),
                "input_index": input_idx,
                "t_start": bgrow.get("t_start"),
                "t_end": bgrow.get("t_end"),
                "preset": bgrow.get("background_image_preset"),
            }
        )

    visuals = inter.get("visual_timeline") if isinstance(inter.get("visual_timeline"), list) else []
    visual_inputs: list[tuple[dict[str, Any], int, str]] = []
    visual_input_by_source: dict[str, tuple[int, str]] = {}
    for v in visuals:
        original_src = Path(str(v.get("source_path") or ""))
        src = _resolve_media_source(original_src)
        if not src.exists():
            msg = f"missing_visual:{src}"
            if strict:
                raise FileNotFoundError(msg)
            warnings.append(msg)
            debug_report["visual_inputs"].append(
                {
                    "element_id": v.get("element_id"),
                    "source_path": str(original_src),
                    "resolved_path": str(src),
                    "status": "missing",
                }
            )
            continue
        kind = _media_kind(str(src), str(v.get("type", "")))
        if kind not in {"image", "gif", "video"}:
            warnings.append(f"skip_non_visual_input:{src}")
            debug_report["visual_inputs"].append(
                {
                    "element_id": v.get("element_id"),
                    "source_path": str(original_src),
                    "resolved_path": str(src),
                    "status": "non_visual",
                    "kind": kind,
                }
            )
            continue
        if not _probe_decodable(src, kind):
            warnings.append(f"skip_undecodable_visual:{src}")
            debug_report["visual_inputs"].append(
                {
                    "element_id": v.get("element_id"),
                    "source_path": str(original_src),
                    "resolved_path": str(src),
                    "status": "undecodable",
                    "kind": kind,
                }
            )
            continue
        src_key = str(src.resolve())
        if src_key in visual_input_by_source:
            idx, kind = visual_input_by_source[src_key]
        else:
            idx = next_input_idx
            next_input_idx += 1
            if kind == "image":
                cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(src)]
            elif kind == "gif":
                cmd += ["-stream_loop", "-1", "-i", str(src)]
            else:
                cmd += ["-stream_loop", "-1", "-i", str(src)]
            visual_input_by_source[src_key] = (idx, kind)
        visual_inputs.append((v, idx, kind))
        debug_report["visual_inputs"].append(
            {
                "element_id": v.get("element_id"),
                "source_path": str(original_src),
                "resolved_path": str(src),
                "status": "included",
                "kind": kind,
                "input_index": idx,
                "t_start": v.get("t_start"),
                "t_end": v.get("t_end"),
            }
        )

    base_visual = inter.get("base_visual") if isinstance(inter.get("base_visual"), dict) else {}
    base_visual_input: tuple[dict[str, Any], int, str] | None = None
    if base_visual:
        base_src_text = str(base_visual.get("source_path") or "").strip()
        base_src = _resolve_media_source(Path(base_src_text)) if base_src_text else Path("")
        base_kind = _media_kind(str(base_src), str(base_visual.get("type") or "video"))
        if base_src.exists() and base_kind in {"video", "gif", "image"} and _probe_decodable(base_src, base_kind):
            base_idx = next_input_idx
            next_input_idx += 1
            if base_kind == "image":
                cmd += ["-loop", "1", "-framerate", str(fps), "-i", str(base_src)]
            else:
                cmd += ["-stream_loop", "-1", "-i", str(base_src)]
            base_visual_input = (base_visual, base_idx, base_kind)
            debug_report["base_visual_input"] = {
                "element_id": base_visual.get("element_id"),
                "source_path": base_src_text,
                "resolved_path": str(base_src),
                "kind": base_kind,
                "input_index": base_idx,
            }
        else:
            warnings.append(f"skip_base_visual:{base_src_text}")

    audio = inter.get("audio") if isinstance(inter.get("audio"), dict) else {}
    audio_src_text = str(audio.get("source_path") or "").strip()
    audio_src = Path(audio_src_text) if audio_src_text else None
    audio_idx = None
    if audio_src and audio_src.exists():
        audio_idx = next_input_idx
        next_input_idx += 1
        cmd += ["-i", str(audio_src)]
    elif strict and audio_src_text:
        raise FileNotFoundError(f"missing_audio:{audio_src}")

    filters = ["[0:v]setpts=PTS-STARTPTS[base0]"]
    base = "base0"

    for i, bgrow in enumerate(background_rows):
        ts = max(0.0, min(duration, _f(bgrow.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _f(bgrow.get("t_end"), ts)))
        if te <= ts:
            continue
        opacity = max(0.0, min(1.0, _f(bgrow.get("opacity"), 1.0)))
        label = f"bg{i}"
        if i in bg_inputs:
            input_idx = bg_inputs[i]
            seg_dur = te - ts
            filters.append(
                f"[{input_idx}:v]trim=start=0:duration={seg_dur},setpts=PTS-STARTPTS+{ts}/TB,"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},format=rgba,colorchannelmixer=aa={opacity}[{label}]"
            )
        else:
            filters.append(_background_filter(bgrow, width, height, duration, fps, opacity, label))
        out_label = f"v_bg{i}"
        filters.append(f"[{base}][{label}]overlay=0:0:enable='between(t\\,{ts}\\,{te})'[{out_label}]")
        base = out_label

    if base_visual_input is not None:
        bv, input_idx, kind = base_visual_input
        layout = bv.get("layout") if isinstance(bv.get("layout"), dict) else {}
        x = _f(layout.get("x"), 0.0)
        y = _f(layout.get("y"), 544.0)
        w = max(1, int(_f(layout.get("width"), 1080)))
        h = max(1, int(_f(layout.get("height"), 800)))
        fit = str(layout.get("fit") or "cover").lower()
        force = "increase" if fit == "cover" else "decrease"
        opacity = max(0.0, min(1.0, _f(layout.get("opacity"), 1.0)))
        chain = f"[{input_idx}:v]"
        if kind == "gif":
            chain += f"fps={fps},trim=start=0:duration={duration},setpts=N/({fps}*TB),format=rgba"
        else:
            chain += f"trim=start=0:duration={duration},setpts=PTS-STARTPTS,format=rgba"
        chain += f",scale={w}:{h}:force_original_aspect_ratio={force}"
        if fit == "cover":
            chain += f",crop={w}:{h}"
        if opacity < 0.999:
            chain += f",colorchannelmixer=aa={opacity}"
        filters.append(f"{chain}[base_visual]")
        out_label = "v_base_visual"
        filters.append(f"[{base}][base_visual]overlay={x}+({w}-overlay_w)/2:{y}+({h}-overlay_h)/2[{out_label}]")
        base = out_label

    for i, (v, input_idx, kind) in enumerate(visual_inputs):
        ts = max(0.0, min(duration, _f(v.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _f(v.get("t_end"), ts)))
        if te <= ts:
            continue
        layout = v.get("layout") if isinstance(v.get("layout"), dict) else {}
        x = _f(layout.get("x"), 0.0)
        y = _f(layout.get("y"), 544.0)
        w = max(1, int(_f(layout.get("width"), 1080)))
        h = max(1, int(_f(layout.get("height"), 800)))
        opacity = max(0.0, min(1.0, _f(layout.get("opacity"), 1.0)))
        animation = v.get("animation") if isinstance(v.get("animation"), dict) else {}
        anim_type = str(animation.get("type") or "none").lower()
        transition_in = v.get("transition_in") if isinstance(v.get("transition_in"), dict) else {}
        transition_out = v.get("transition_out") if isinstance(v.get("transition_out"), dict) else {}
        tin_type = str(transition_in.get("type") or "cut").lower()
        tout_type = str(transition_out.get("type") or "cut").lower()
        tin_dur = max(0.0, min(1.2, _f(transition_in.get("duration"), 0.0)))
        tout_dur = max(0.0, min(1.2, _f(transition_out.get("duration"), 0.0)))
        seg_dur = te - ts
        chain = f"[{input_idx}:v]"
        if kind == "gif":
            chain += f"fps={fps},trim=start=0:duration={seg_dur},setpts=N/({fps}*TB)+{ts}/TB,format=rgba"
        else:
            chain += f"trim=start=0:duration={seg_dur},setpts=PTS-STARTPTS+{ts}/TB,format=rgba"
        fit = str(layout.get("fit") or "contain").lower()
        force = "increase" if fit == "cover" else "decrease"
        scale_w, scale_h = w, h
        if anim_type in {"subtle_zoom", "subtle_zoom_out", "pulse", "card_lift", "tilt_float"} or tin_type in {"zoom", "zoom_blur", "blur_fade"}:
            scale_w = int(math.ceil(w * 1.06))
            scale_h = int(math.ceil(h * 1.06))
        chain += f",scale={scale_w}:{scale_h}:force_original_aspect_ratio={force}"
        if fit == "cover":
            chain += f",crop={w}:{h}"
        if tin_type in {"fade", "blur_fade", "dip"} and tin_dur > 0:
            chain += f",fade=t=in:st=0:d={tin_dur}:alpha=1"
        if tout_type in {"fade", "blur_fade", "dip"} and tout_dur > 0:
            chain += f",fade=t=out:st={max(0.0, seg_dur - tout_dur)}:d={tout_dur}:alpha=1"
        if tin_type == "pop":
            chain += ",eq=brightness=0.018:saturation=1.08"
        elif tin_type in {"zoom", "zoom_blur"}:
            chain += ",eq=contrast=1.04"
        elif tin_type == "flash":
            chain += ",eq=brightness=0.055:saturation=1.12"
        elif tin_type == "blur_fade":
            chain += ",boxblur=luma_radius=2:luma_power=1:chroma_radius=1:chroma_power=1"
        if opacity < 0.999:
            chain += f",colorchannelmixer=aa={opacity}"
        label = f"vis{i}"
        filters.append(f"{chain}[{label}]")
        out_label = f"v_vis{i}"
        overlay_x = f"{x}+({w}-overlay_w)/2"
        overlay_y = f"{y}+({h}-overlay_h)/2"
        if anim_type == "float":
            amp = max(4.0, min(28.0, _f(animation.get("amplitude"), 12.0)))
            overlay_y = f"{overlay_y}+{amp}*sin(2*PI*(t-{ts})/2.4)"
        elif anim_type == "pulse":
            overlay_x = f"{overlay_x}+8*sin(2*PI*(t-{ts})/0.9)"
            overlay_y = f"{overlay_y}-8*sin(2*PI*(t-{ts})/0.9)"
        elif anim_type == "subtle_zoom":
            overlay_x = f"{overlay_x}-min(max((t-{ts})/{max(seg_dur, 0.1)}\\,0)\\,1)*18"
            overlay_y = f"{overlay_y}-min(max((t-{ts})/{max(seg_dur, 0.1)}\\,0)\\,1)*18"
        elif anim_type == "subtle_zoom_out":
            overlay_x = f"{overlay_x}-18*(1-min(max((t-{ts})/{max(seg_dur, 0.1)}\\,0)\\,1))"
            overlay_y = f"{overlay_y}-18*(1-min(max((t-{ts})/{max(seg_dur, 0.1)}\\,0)\\,1))"
        elif anim_type == "drift":
            x_from = _f(animation.get("x_from"), -18.0)
            x_to = _f(animation.get("x_to"), 18.0)
            progress = f"min(max((t-{ts})/{max(seg_dur, 0.1)}\\,0)\\,1)"
            overlay_x = f"{overlay_x}+({x_from}+({x_to - x_from})*{progress})"
        elif anim_type == "card_lift":
            y_from = _f(animation.get("y_from"), 26.0)
            y_to = _f(animation.get("y_to"), 0.0)
            progress = f"min(max((t-{ts})/0.45\\,0)\\,1)"
            overlay_y = f"{overlay_y}+({y_from}+({y_to - y_from})*{progress})"
        elif anim_type == "tilt_float":
            amp = max(4.0, min(22.0, _f(animation.get("amplitude"), 8.0)))
            overlay_x = f"{overlay_x}+{amp}*sin(2*PI*(t-{ts})/2.8)"
            overlay_y = f"{overlay_y}+{amp * 0.55}*cos(2*PI*(t-{ts})/3.2)"
        elif anim_type == "shake":
            amp = max(3.0, min(18.0, _f(animation.get("amplitude"), 8.0)))
            dur = max(0.08, min(0.45, _f(animation.get("duration"), 0.18)))
            gate = f"if(lt(t-{ts}\\,{dur})\\,1\\,0)"
            overlay_x = f"{overlay_x}+{amp}*sin(70*(t-{ts}))*{gate}"
            overlay_y = f"{overlay_y}+{amp * 0.55}*cos(84*(t-{ts}))*{gate}"
        if tin_type in {"slide", "whip"}:
            direction = str(transition_in.get("direction") or "up").lower()
            distance = _f(transition_in.get("distance"), 260.0 if tin_type == "whip" else 80.0)
            progress = f"(1-min(max((t-{ts})/{max(tin_dur, 0.16 if tin_type == 'whip' else 0.22)}\\,0)\\,1))"
            if direction == "up":
                overlay_y = f"{overlay_y}+{distance}*{progress}"
            elif direction == "down":
                overlay_y = f"{overlay_y}-{distance}*{progress}"
            elif direction == "left":
                overlay_x = f"{overlay_x}+{distance}*{progress}"
            else:
                overlay_x = f"{overlay_x}-{distance}*{progress}"
        elif tin_type in {"zoom", "zoom_blur"}:
            overlay_x = f"{overlay_x}-16*(1-min(max((t-{ts})/{max(tin_dur, 0.18)}\\,0)\\,1))"
            overlay_y = f"{overlay_y}-16*(1-min(max((t-{ts})/{max(tin_dur, 0.18)}\\,0)\\,1))"
        if layout.get("shadow"):
            shadow_label = f"v_shadow{i}"
            shadow_alpha = 0.26 if str(animation.get("intensity") or "").lower() != "high" else 0.34
            filters.append(
                f"[{base}]drawbox=x={max(0.0, x + 16)}:y={max(0.0, y + 20)}:w={w}:h={h}:"
                f"color=black@{shadow_alpha}:t=fill:enable='between(t\\,{ts}\\,{te})'[{shadow_label}]"
            )
            base = shadow_label
        filters.append(f"[{base}][{label}]overlay={overlay_x}:{overlay_y}:enable='between(t\\,{ts}\\,{te})'[{out_label}]")
        base = out_label

    font = _fontfile()
    font_part = f"fontfile='{font}':" if font else ""
    for i, c in enumerate(inter.get("caption_timeline") or []):
        ts = max(0.0, min(duration, _f(c.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _f(c.get("t_end"), ts)))
        text = str(c.get("text", "")).strip()
        if te <= ts or not text:
            warnings.append(f"skip_caption_invalid:{i}")
            continue
        layout = c.get("layout") if isinstance(c.get("layout"), dict) else {}
        style = c.get("style") if isinstance(c.get("style"), dict) else {}
        animation = c.get("animation") if isinstance(c.get("animation"), dict) else {}
        x = _f(layout.get("x"), 90.0)
        y = _f(layout.get("y"), 1450.0)
        w = _f(layout.get("width"), 900.0)
        h = _f(layout.get("height"), 300.0)
        base = _append_caption_filters(
            filters,
            base,
            i,
            text=text,
            ts=ts,
            te=te,
            x=x,
            y=y,
            w=w,
            h=h,
            style=style,
            animation=animation,
            font_part=font_part,
        )
        debug_report["caption_filters"] += 1

    if audio_idx is not None:
        vol = _f(audio.get("volume"), 1.0)
        filters.append(f"[{audio_idx}:a]atrim=start=0:duration={duration},asetpts=PTS-STARTPTS,volume={vol}[a0]")
        maps = ["-map", f"[{base}]", "-map", "[a0]"]
    else:
        maps = ["-map", f"[{base}]", "-an"]

    graph = ";".join(filters)
    suffix = maps + ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(fps), str(out)]
    render_cmd: list[str]
    graph_path: str | None = None
    if len(graph) > 6000:
        with tempfile.NamedTemporaryFile("w", suffix=".ffgraph", delete=False, encoding="utf-8") as f:
            f.write(graph)
            graph_path = f.name
        render_cmd = cmd + ["-filter_complex_script", graph_path] + suffix
    else:
        render_cmd = cmd + ["-filter_complex", graph] + suffix
    try:
        _run_ffmpeg_quiet(render_cmd)
    except subprocess.CalledProcessError as exc:
        if _is_oom_error(exc):
            print("[A2V_V3_RENDER] OOM detected, retrying with chunked large-render mode.")
            try:
                _render_large_mode(inter, out)
                return out
            except Exception as retry_exc:
                raise subprocess.CalledProcessError(
                    exc.returncode,
                    exc.cmd,
                    output=exc.output,
                    stderr=(
                        _stderr_text(exc).strip()[-5000:]
                        + "\n\nLarge-render retry also failed:\n"
                        + str(retry_exc)
                    ),
                ) from retry_exc
        reason = "\n".join(
            [
                "Primary FFmpeg render failed. Safe fallback rendered black video with audio instead of crashing.",
                f"returncode={exc.returncode}",
                "stderr_tail:",
                (exc.stderr or exc.output or "").strip()[-5000:],
                "renderer_warnings:",
                "\n".join(warnings),
            ]
        )
        _safe_fallback_render(
            out=out,
            width=width,
            height=height,
            fps=fps,
            duration=duration,
            audio_src=audio_src if audio_src and audio_src.exists() else None,
            reason=reason,
        )
    finally:
        if graph_path:
            Path(graph_path).unlink(missing_ok=True)
    debug_report["visual_inputs_included"] = sum(1 for row in debug_report["visual_inputs"] if row.get("status") == "included")
    debug_report["warnings"] = warnings
    out.with_suffix(".render_report.json").write_text(json.dumps(debug_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--inter-json", required=True)
    parser.add_argument("--media-json", required=True)
    parser.add_argument("--output", default="insta_edit.mp4")
    args = parser.parse_args()
    print(render_into_video(args.inter_json, args.media_json, args.output))
