from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running this file directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vasp.core.elements import Caption, Figure, GIF, Image, Music, Sfx, Timing, Video


def _color_hex(rgb: list[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _escape_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", r"\'")


def _ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


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


def _write_output_json(input_path: Path, payload: dict) -> Path:
    out_path = input_path.with_name(input_path.stem + "_output.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return out_path


def _overlay_xy_center(x: float, y: float) -> tuple[str, str]:
    """Treat x,y as center; return overlay expressions for top-left."""
    return (f"{x}-overlay_w/2", f"{y}-overlay_h/2")


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
    fontfile = str(font_path) if font_path.exists() else ""

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
        drawtext = (
            f"drawtext=fontfile={fontfile}:"
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
    if actions:
        filters = ["[0:v]setpts=PTS-STARTPTS[base0]"]
        base_label = "base0"
        for idx, action in enumerate(actions):
            if action.get("op") != "show":
                continue
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            scale = float(params.get("scale", 1.0))
            trim_in = float(params.get("trim_in", 0.0))
            trim_out = params.get("trim_out")
            length = element.get("length")
            if length is not None:
                trim_out = min(float(trim_out) if trim_out is not None else float(length), float(length))
            seg_dur = max(0.0, t_end - t_start)
            if trim_out is not None:
                seg_dur = min(seg_dur, max(0.0, float(trim_out) - trim_in))
            label = f"ov{idx}"
            filters.append(
                f"[1:v]trim=start={trim_in}:duration={seg_dur},setpts=PTS-STARTPTS,"
                f"scale=iw*{scale}:ih*{scale}[{label}]"
            )
            out_label = f"v{idx}"
            filters.append(
                f"[{base_label}][{label}]overlay={x_expr}:{y_expr}:enable='between(t\\,{t_start}\\,{t_end})'[{out_label}]"
            )
            base_label = out_label
        filter_str = ";".join(filters)
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
    # Alpha mask that rounds corners with radius r.
    # Avoid unsupported logical ops by using numeric comparisons.
    expr = (
        "if(lte(pow(min(X\\,W-1-X)-%d\\,2)+pow(min(Y\\,H-1-Y)-%d\\,2)\\,pow(%d\\,2))"
        "\\,255\\,"
        "if(lt(min(X\\,W-1-X)\\,%d)+lt(min(Y\\,H-1-Y)\\,%d)\\,0\\,255))"
        % (r, r, r, r, r)
    )
    return f"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{expr}'"


def _fontfile_for(style: str, weight: str) -> str:
    base = Path("C:/Windows/Fonts/arial.ttf")
    bold = Path("C:/Windows/Fonts/arialbd.ttf")
    italic = Path("C:/Windows/Fonts/ariali.ttf")
    bold_italic = Path("C:/Windows/Fonts/arialbi.ttf")

    style = (style or "normal").lower()
    weight = (weight or "regular").lower()

    if "italic" in style and "bold" in weight and bold_italic.exists():
        return str(bold_italic)
    if "italic" in style and italic.exists():
        return str(italic)
    if "bold" in weight and bold.exists():
        return str(bold)
    if base.exists():
        return str(base)
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

    filters = ["[0:v]setpts=PTS-STARTPTS[base0]"]
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
        x_expr, y_expr = _overlay_xy_center(x, y)

        for action in actions:
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            scale = float(params.get("scale", 1.0))
            round_corners = int(params.get("round_corners", 0))

            chain = f"[{input_index}:v]scale=iw*{scale}:ih*{scale}"
            rounded = _rounded_corners_filter(round_corners)
            if rounded:
                chain += f",{rounded}"
            label = f"e{element_id}_{int(t_start*1000)}"
            filters.append(f"{chain}[{label}]")
            out_label = f"v{len(filters)}"
            filters.append(
                f"[{base_label}][{label}]overlay={x_expr}:{y_expr}:enable='between(t\\,{t_start}\\,{t_end})'[{out_label}]"
            )
            base_label = out_label

        input_index += 1

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{base_label}]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


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

    # Audio input (single for now)
    audio_input_index = None
    audio_element = None
    if audio_elements:
        audio_element = audio_elements[0]
        audio_path = Path(audio_element["source_uri"])
        if not audio_path.exists():
            if strict:
                raise FileNotFoundError(audio_path)
        else:
            audio_input_index = 1 + len(image_inputs)
            cmd += ["-i", str(audio_path)]

    # Build filter graph
    filters: list[str] = ["[0:v]setpts=PTS-STARTPTS[base0]"]
    base_label = "base0"
    # Visual overlays (image/gif/video)
    for element, input_index in image_input_map:
        actions = sorted(actions_by_id.get(element["id"], []), key=lambda a: a.get("t_start", 0.0))
        x = element.get("transform", {}).get("x", 0)
        y = element.get("transform", {}).get("y", 0)
        x_expr, y_expr = _overlay_xy_center(x, y)

        for action in actions:
            if action.get("op") != "show":
                continue
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            scale = float(params.get("scale", 1.0))
            trim_in = float(params.get("trim_in", 0.0))
            trim_out = params.get("trim_out")
            round_corners = int(params.get("round_corners", 0))

            seg_dur = max(0.0, t_end - t_start)
            if trim_out is not None:
                seg_dur = min(seg_dur, max(0.0, float(trim_out) - trim_in))
            chain = (
                f"[{input_index}:v]trim=start={trim_in}:duration={seg_dur},setpts=PTS-STARTPTS,"
                f"scale=iw*{scale}:ih*{scale}"
            )
            rounded = _rounded_corners_filter(round_corners)
            if rounded:
                chain += f",{rounded}"
            label = f"img_{element['id']}_{int(t_start*1000)}"
            filters.append(f"{chain}[{label}]")
            out_label = f"v{len(filters)}"
            filters.append(
                f"[{base_label}][{label}]overlay={x_expr}:{y_expr}:enable='between(t\\,{t_start}\\,{t_end})'[{out_label}]"
            )
            base_label = out_label

    # Caption drawtext
    for element in caption_elements:
        actions = sorted(actions_by_id.get(element["id"], []), key=lambda a: a.get("t_start", 0.0))
        x = element.get("transform", {}).get("x", 0)
        y = element.get("transform", {}).get("y", 0)
        text = _escape_text(element.get("text", ""))
        x_expr = f"{x}-text_w/2"
        y_expr = f"{y}-text_h/2"

        for action in actions:
            if action.get("op") != "show":
                continue
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            font_size = int(params.get("font_size", 48))
            font_weight = params.get("font_weight", "regular")
            font_style = params.get("font_style", "normal")
            color = params.get("color", "#FFFFFF")
            fontfile = _fontfile_for(font_style, font_weight)

            draw = (
                f"drawtext=fontfile={fontfile}:text='{text}':"
                f"x={x_expr}:y={y_expr}:fontcolor={color}:fontsize={font_size}:"
                f"enable='between(t\\,{t_start}\\,{t_end})'"
            )
            out_label = f"v{len(filters)}"
            filters.append(f"[{base_label}]{draw}[{out_label}]")
            base_label = out_label

    # Audio chain (optional)
    if audio_input_index is not None and audio_element is not None:
        actions = actions_by_id.get(audio_element["id"], [])
        volume = audio_element.get("volume", 1.0)
        for action in actions:
            params = action.get("params", {})
            if "volume" in params:
                volume = params.get("volume", volume)
        start_offset = 0.0
        if audio_element.get("metadata", {}).get("crop_loudest"):
            start_offset = _find_loudest_segment(Path(audio_element["source_uri"]), duration)
        audio_filters: list[str] = []
        seg_labels: list[str] = []
        for idx, action in enumerate(actions):
            if action.get("op") not in ("play", "show"):
                continue
            t_start = float(action.get("t_start", 0.0))
            t_end = float(action.get("t_end", 0.0))
            params = action.get("params", {})
            trim_in = float(params.get("trim_in", 0.0))
            trim_out = params.get("trim_out")
            length = audio_element.get("length")
            if length is not None:
                trim_out = min(float(trim_out) if trim_out is not None else float(length), float(length))
            seg_dur = max(0.0, t_end - t_start)
            if trim_out is not None:
                seg_dur = min(seg_dur, max(0.0, float(trim_out) - trim_in))
            seg_label = f"a{idx}"
            delay_ms = int(t_start * 1000)
            trim_clause = f"atrim=start={trim_in}:duration={seg_dur}"
            audio_filters.append(
                f"[{audio_input_index}:a]{trim_clause},asetpts=PTS-STARTPTS,"
                f"volume={params.get('volume', volume)},adelay={delay_ms}|{delay_ms}[{seg_label}]"
            )
            seg_labels.append(f"[{seg_label}]")

        if not seg_labels:
            audio_filters.append(
                f"[{audio_input_index}:a]atrim=start={start_offset}:duration={duration},"
                f"asetpts=PTS-STARTPTS,volume={volume}[a]"
            )
            seg_labels = ["[a]"]

        if len(seg_labels) > 1:
            audio_filters.append(f"{''.join(seg_labels)}amix=inputs={len(seg_labels)}[a]")
            out_label = "[a]"
        else:
            out_label = seg_labels[0]

        filters.extend(audio_filters)

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{base_label}]",
    ]
    if audio_input_index is not None and audio_element is not None:
        cmd += ["-map", out_label]
    cmd += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]

    subprocess.run(cmd, check=True)
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
    for idx, action in enumerate(actions):
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


def render_from_json(input_path: str, *, strict: bool = False) -> Path:
    path = Path(input_path)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["_input_path"] = str(path)

    properties_path = payload.get("properties_path")
    if not properties_path:
        raise ValueError("properties_path is required in the actions JSON.")
    with open(properties_path, "r", encoding="utf-8") as handle:
        props_payload = json.load(handle)

    output_path = Path(payload["video"]["output_path"])
    _ensure_output_dir(output_path)

    actions_by_id = {entry["element_id"]: entry.get("actions", []) for entry in payload["elements"]}
    elements_props = props_payload["elements"]
    elements_list = [item["properties"] for item in elements_props]

    if len(elements_list) > 1:
        return _render_multi_elements(payload, output_path, elements_list, actions_by_id, strict=strict)

    element = elements_list[0]
    actions = actions_by_id[element["id"]]
    element_type = element["type"]

    if element_type == "caption":
        _render_caption_words(payload, output_path, element, actions)
        return output_path

    if element_type == "image":
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
    from vasp.core.serialization import serialize_element_json

    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", help="Path to the input JSON.")
    parser.add_argument("--strict", action="store_true", help="Fail if media is missing.")
    parser.add_argument(
        "--serialize-only",
        action="store_true",
        help="Only generate elements.json and elementsProps.json.",
    )
    args = parser.parse_args()

    actions_json, props_json = serialize_element_json(args.input_json)
    input_path = Path(args.input_json)
    actions_path = input_path.with_name("elements.json")
    props_path = input_path.with_name("elementsProps.json")
    actions_json["properties_path"] = str(props_path)
    with open(actions_path, "w", encoding="utf-8") as handle:
        json.dump(actions_json, handle, indent=2)
    with open(props_path, "w", encoding="utf-8") as handle:
        json.dump(props_json, handle, indent=2)

    if not args.serialize_only:
        render_from_json(str(actions_path), strict=args.strict)


if __name__ == "__main__":
    main()
