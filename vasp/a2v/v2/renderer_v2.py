from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _to_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _escape_text(text: str) -> str:
    return (
        text.replace("'", "")
        .replace("\n", " ")
        .replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace(";", r"\;")
        .replace("%", r"\%")
    )


def _escape_fontfile(path: str) -> str:
    return path.replace("\\", "/").replace(":", r"\:")


def _fontfile() -> str:
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return _escape_fontfile(c)
    return ""


def _hex_color(s: str, fallback: str) -> str:
    v = str(s or "").strip()
    if v.startswith("#") and len(v) in (7, 9):
        return "0x" + v[1:]
    return fallback


def _rgba_to_box(v: str) -> tuple[str, float]:
    s = str(v or "").strip()
    if s.startswith("rgba(") and s.endswith(")"):
        inner = s[5:-1]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 4:
            try:
                r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
                a = max(0.0, min(1.0, float(parts[3])))
                return f"0x{r:02X}{g:02X}{b:02X}", a
            except Exception:
                pass
    return _hex_color(s, "0x000000"), 0.45


def _caption_box_filter(style: dict[str, Any]) -> str:
    bg_raw = str(style.get("background_color") or "").strip()
    if bg_raw.lower() in {"", "none", "transparent"}:
        return ""
    bg_color, bg_alpha = _rgba_to_box(bg_raw)
    if "background_opacity" in style:
        bg_alpha = max(0.0, min(1.0, _to_float(style.get("background_opacity"), bg_alpha)))
    if bg_alpha <= 0.01:
        return ""
    return f":box=1:boxcolor={bg_color}@{bg_alpha}:boxborderw=14"


def _background_chain(row: dict[str, Any], width: int, height: int, duration: float, fps: int, label: str) -> str:
    bg_type = str(row.get("type") or "solid").lower()
    color = _hex_color(str(row.get("color") or "#000000"), "0x000000")
    secondary = _hex_color(str(row.get("secondary_color") or row.get("color") or "#111111"), "0x111111")
    opacity = max(0.0, min(1.0, _to_float(row.get("opacity"), 1.0)))
    grain = max(0.0, min(0.35, _to_float(row.get("grain"), 0.0)))
    vignette = max(0.0, min(0.85, _to_float(row.get("vignette"), 0.0)))
    chain = f"color=c={color}:s={width}x{height}:d={duration}:r={fps},format=rgba"
    if bg_type in {"gradient", "pattern", "blur"}:
        chain += f",drawbox=x=0:y=0:w=iw:h=ih/3:color={secondary}@0.24:t=fill,drawbox=x=0:y=ih*2/3:w=iw:h=ih/3:color={secondary}@0.18:t=fill"
    if bg_type in {"vignette", "blur"} or vignette > 0:
        strength = max(vignette, 0.25)
        chain += f",drawbox=x=0:y=0:w=iw:h=ih/7:color=black@{min(0.6, strength)}:t=fill,drawbox=x=0:y=ih*6/7:w=iw:h=ih/7:color=black@{min(0.7, strength + 0.08)}:t=fill"
    if grain > 0:
        alpha = min(0.16, grain)
        chain += f",drawbox=x=0:y=ih*0.31:w=iw:h=1:color=white@{alpha}:t=fill,drawbox=x=0:y=ih*0.63:w=iw:h=1:color=black@{alpha}:t=fill"
    chain += f",colorchannelmixer=aa={opacity}[{label}]"
    return chain


def _visual_type_from_source(source_uri: str, declared: str) -> str:
    ext = Path(str(source_uri or "")).suffix.lower()
    if ext == ".gif":
        return "gif"
    if ext in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
        return "video"
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return "image"
    d = str(declared or "").lower()
    if "gif" in d or "sticker" in d:
        return "gif"
    if "video" in d:
        return "video"
    return "image"


def validate_inter_v2(inter: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    video = inter.get("video")
    if not isinstance(video, dict):
        return ["video missing"]
    if _to_float(video.get("duration"), 0.0) <= 0:
        errs.append("video duration invalid")
    audio_ok = False
    audio = inter.get("audio_track")
    if isinstance(audio, dict) and str(audio.get("source_uri", "")).strip():
        audio_ok = True
    if not audio_ok:
        elements = inter.get("elements", [])
        if isinstance(elements, list):
            for e in elements:
                if not isinstance(e, dict):
                    continue
                if str(e.get("type", "")).lower() not in {"music", "audio"}:
                    continue
                src = e.get("source_uri") or ((e.get("properties") or {}).get("source_uri"))
                if str(src or "").strip():
                    audio_ok = True
                    break
    if not audio_ok:
        errs.append("audio track missing")
    return errs


def render_inter_v2(inter_path: str | Path) -> Path:
    inter_p = Path(inter_path)
    inter = json.loads(inter_p.read_text(encoding="utf-8"))
    errs = validate_inter_v2(inter)
    if errs:
        raise ValueError("inter_v2 invalid: " + "; ".join(errs))

    video = inter["video"]
    width = int(_to_float(video.get("width"), _to_float((video.get("size") or {}).get("width"), 1080)))
    height = int(_to_float(video.get("height"), _to_float((video.get("size") or {}).get("height"), 1920)))
    fps = int(_to_float(video.get("fps"), 30))
    duration = _to_float(video.get("duration"), 0.0)
    bg_raw = video.get("bg_color", "#000000")
    if isinstance(bg_raw, list) and len(bg_raw) >= 3:
        try:
            bg = f"#{int(bg_raw[0]):02X}{int(bg_raw[1]):02X}{int(bg_raw[2]):02X}"
        except Exception:
            bg = "#000000"
    else:
        bg = str(bg_raw)
    output_path = Path(str(video.get("output_path", "output/final_v2.mp4")))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    visuals = inter.get("visual_timeline", []) if isinstance(inter.get("visual_timeline"), list) else []
    backgrounds = inter.get("background_timeline", []) if isinstance(inter.get("background_timeline"), list) else []
    elements = inter.get("elements", []) if isinstance(inter.get("elements"), list) else []
    caption_track = inter.get("caption_track", {}) if isinstance(inter.get("caption_track"), dict) else {}
    cues = caption_track.get("cues", []) if isinstance(caption_track.get("cues"), list) else []
    style = caption_track.get("style", {}) if isinstance(caption_track.get("style"), dict) else {}
    audio = inter.get("audio_track", {})
    if not isinstance(audio, dict) or not str(audio.get("source_uri", "")).strip():
        # old inter schema fallback
        for e in elements:
            if not isinstance(e, dict):
                continue
            if str(e.get("type", "")).lower() not in {"music", "audio"}:
                continue
            src = e.get("source_uri") or ((e.get("properties") or {}).get("source_uri"))
            if src:
                audio = {"source_uri": src, "t_start": 0.0, "t_end": duration, "volume": 1.0}
                break
    audio_src = Path(str(audio.get("source_uri", "")))
    if not audio_src.exists():
        raise FileNotFoundError(f"audio source missing: {audio_src}")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg}:s={width}x{height}:d={duration}:r={fps}",
    ]

    # Prefer explicit visual action tracks if present in elements.
    action_visuals: list[dict[str, Any]] = []
    for e in elements:
        if not isinstance(e, dict):
            continue
        et = str(e.get("type", "")).lower()
        if et not in {"image", "video", "gif", "sticker"}:
            continue
        acts = e.get("actions")
        if not isinstance(acts, list):
            continue
        for a in acts:
            if not isinstance(a, dict) or str(a.get("op", "")).lower() != "show":
                continue
            params = a.get("params") if isinstance(a.get("params"), dict) else {}
            layout = params.get("layout") if isinstance(params.get("layout"), dict) else {}
            if not layout:
                # old inter action params use center x/y + scale
                cx = _to_float(params.get("x"), 540.0)
                cy = _to_float(params.get("y"), 944.0)
                layout = {"x": cx - 540.0, "y": cy - 400.0, "width": 1080.0, "height": 800.0, "opacity": _to_float(params.get("alpha"), 1.0)}
            action_visuals.append(
                {
                    "element_id": e.get("element_id"),
                    "source_uri": e.get("source_uri") or ((e.get("properties") or {}).get("source_uri")),
                    "type": e.get("type"),
                    "t_start": a.get("t_start"),
                    "t_end": a.get("t_end"),
                    "layout": layout,
                }
            )
    if action_visuals:
        visuals = action_visuals

    if isinstance(caption_track.get("actions"), list) and caption_track.get("actions"):
        cues = []
        for a in caption_track.get("actions", []):
            if not isinstance(a, dict) or str(a.get("op", "")).lower() != "show":
                continue
            params = a.get("params") if isinstance(a.get("params"), dict) else {}
            cues.append(
                {
                    "text": params.get("text", ""),
                    "t_start": a.get("t_start"),
                    "t_end": a.get("t_end"),
                    "layout": params.get("layout", {}),
                }
            )
    elif not cues:
        # old inter schema: caption is an element with actions
        for e in elements:
            if not isinstance(e, dict) or str(e.get("type", "")).lower() != "caption":
                continue
            acts = e.get("actions")
            if not isinstance(acts, list):
                continue
            for a in acts:
                if not isinstance(a, dict) or str(a.get("op", "")).lower() != "show":
                    continue
                p = a.get("params") if isinstance(a.get("params"), dict) else {}
                lx = _to_float(p.get("x"), 90.0)
                ly = _to_float(p.get("y"), 1450.0)
                lay = p.get("layout") if isinstance(p.get("layout"), dict) else {"x": lx, "y": ly, "width": 900.0, "height": 300.0}
                cues.append({"text": p.get("text", ""), "t_start": a.get("t_start"), "t_end": a.get("t_end"), "layout": lay})
            break

    visual_inputs: list[tuple[dict[str, Any], int, str]] = []
    skipped_visuals = 0
    for v in visuals:
        if not isinstance(v, dict):
            skipped_visuals += 1
            continue
        src = Path(str(v.get("source_uri", "")))
        if not src.exists():
            skipped_visuals += 1
            continue
        vtype = _visual_type_from_source(str(src), str(v.get("type", "")))
        idx = 1 + len(visual_inputs)
        if vtype == "image":
            cmd += ["-loop", "1", "-t", str(duration), "-i", str(src)]
        elif vtype == "gif":
            cmd += ["-stream_loop", "-1", "-i", str(src)]
        else:
            cmd += ["-i", str(src)]
        visual_inputs.append((v, idx, vtype))

    audio_input_idx = 1 + len(visual_inputs)
    cmd += ["-i", str(audio_src)]

    filters: list[str] = ["[0:v]setpts=PTS-STARTPTS[base0]"]
    base_label = "base0"
    visual_count = 0

    for i, bgrow in enumerate(backgrounds):
        if not isinstance(bgrow, dict):
            continue
        ts = max(0.0, min(duration, _to_float(bgrow.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _to_float(bgrow.get("t_end"), duration)))
        if te <= ts:
            continue
        label = f"bg{i}"
        filters.append(_background_chain(bgrow, width, height, duration, fps, label))
        out_label = f"vbg{i}"
        filters.append(f"[{base_label}][{label}]overlay=0:0:enable='between(t\\,{ts}\\,{te})'[{out_label}]")
        base_label = out_label

    for v, input_idx, vtype in visual_inputs:
        ts = max(0.0, min(duration, _to_float(v.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _to_float(v.get("t_end"), ts)))
        if te <= ts:
            skipped_visuals += 1
            continue
        seg_dur = te - ts
        layout = v.get("layout", {}) if isinstance(v.get("layout"), dict) else {}
        x = _to_float(layout.get("x"), 0.0)
        y = _to_float(layout.get("y"), 544.0)
        bw = _to_float(layout.get("width"), 1080.0)
        bh = _to_float(layout.get("height"), 800.0)
        opacity = max(0.0, min(1.0, _to_float(layout.get("opacity"), 1.0)))

        chain = f"[{input_idx}:v]trim=start=0:duration={seg_dur},setpts=PTS-STARTPTS"
        if vtype == "gif":
            chain = f"[{input_idx}:v]fps=30,trim=start=0:duration={seg_dur},setpts=N/(30*TB),format=rgba"
        chain += f",scale={int(bw)}:{int(bh)}:force_original_aspect_ratio=decrease"
        if opacity < 0.999:
            chain += f",format=rgba,colorchannelmixer=aa={opacity}"
        label = f"vis_{visual_count}"
        filters.append(f"{chain}[{label}]")
        out_label = f"v{len(filters)}"
        ox = f"{x}+({bw}-overlay_w)/2"
        oy = f"{y}+({bh}-overlay_h)/2"
        filters.append(
            f"[{base_label}][{label}]overlay={ox}:{oy}:enable='between(t\\,{ts}\\,{te})'[{out_label}]"
        )
        base_label = out_label
        visual_count += 1

    fontfile = _fontfile()
    font_part = f"fontfile='{fontfile}':" if fontfile else ""
    text_color = _hex_color(style.get("text_color", "#FFFFFF"), "0xFFFFFF")
    stroke_color = _hex_color(style.get("stroke_color", "#000000"), "0x000000")
    box_part = _caption_box_filter(style)
    font_size = max(40, int(_to_float(style.get("font_size"), 64)))
    font_weight = str(style.get("font_weight", "800"))
    is_bold = "bold" in font_weight or font_weight in {"700", "800", "900"}
    caption_count = 0

    for cue in cues:
        if not isinstance(cue, dict):
            continue
        ts = max(0.0, min(duration, _to_float(cue.get("t_start"), 0.0)))
        te = max(0.0, min(duration, _to_float(cue.get("t_end"), ts)))
        if te <= ts:
            continue
        text = _escape_text(str(cue.get("text", "")).strip())
        if not text:
            continue
        lay = cue.get("layout", {}) if isinstance(cue.get("layout"), dict) else {}
        x = _to_float(lay.get("x"), 90.0)
        y = _to_float(lay.get("y"), 1450.0)
        w = _to_float(lay.get("width"), 900.0)
        h = _to_float(lay.get("height"), 300.0)
        xexpr = f"{x}+({w}-text_w)/2"
        yexpr = f"{y}+({h}-text_h)/2"
        draw = (
            f"drawtext={font_part}text='{text}':x={xexpr}:y={yexpr}:"
            f"fontcolor={text_color}:fontsize={font_size}:"
            f"borderw=3:bordercolor={stroke_color}"
            f"{box_part}:"
            f"fix_bounds=1:enable='between(t\\,{ts}\\,{te})'"
        )
        if is_bold:
            draw += ":fontfile='C\\:/Windows/Fonts/arialbd.ttf'" if "fontfile" not in draw else ""
        out_label = f"v{len(filters)}"
        filters.append(f"[{base_label}]{draw}[{out_label}]")
        base_label = out_label
        caption_count += 1

    audio_ts = max(0.0, min(duration, _to_float(audio.get("t_start"), 0.0)))
    audio_te = max(0.0, min(duration, _to_float(audio.get("t_end"), duration)))
    audio_dur = max(0.0, audio_te - audio_ts)
    volume = _to_float(audio.get("volume"), 1.0)
    filters.append(
        f"[{audio_input_idx}:a]atrim=start={audio_ts}:duration={audio_dur},asetpts=PTS-STARTPTS,volume={volume}[a0]"
    )

    filter_graph = ";".join(filters)
    cmd_suffix = [
        "-filter_complex",
        filter_graph,
        "-map",
        f"[{base_label}]",
        "-map",
        "[a0]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        str(output_path),
    ]

    # Use script file for long graphs.
    if len(filter_graph) > 6000:
        with tempfile.NamedTemporaryFile("w", suffix=".ffgraph", delete=False, encoding="utf-8") as f:
            f.write(filter_graph)
            graph_path = f.name
        try:
            subprocess.run(cmd + ["-filter_complex_script", graph_path, "-map", f"[{base_label}]", "-map", "[a0]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), str(output_path)], check=True)
        finally:
            Path(graph_path).unlink(missing_ok=True)
    else:
        subprocess.run(cmd + cmd_suffix, check=True)

    print(
        "[A2V_V2][RENDER] summary: "
        f"visual_clips_rendered={visual_count}, "
        f"caption_cues_rendered={caption_count}, "
        f"skipped_visuals={skipped_visuals}, "
        f"output={str(output_path).replace('\\', '/')}"
    )
    return output_path
