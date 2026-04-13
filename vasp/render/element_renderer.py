from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from vasp.core.elements import Caption, Figure, GIF, Image, Music, Sfx, Timing, Video


def _color_hex(rgb: list[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _escape_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", r"\'")


def _ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_output_json(input_path: Path, payload: dict) -> Path:
    out_path = input_path.with_name(input_path.stem + "_output.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return out_path


def _render_caption_words(payload: dict, output_path: Path) -> None:
    element = payload["element"]
    width = payload["video"]["size"]["width"]
    height = payload["video"]["size"]["height"]
    fps = payload["video"].get("fps", 30)
    bg_color = _color_hex(payload["video"].get("bg_color", [0, 0, 0]))
    text = element["text"]

    words = text.split()
    colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4"]
    rng = random.Random(42)

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
        color = caption.get("metadata", {}).get("color", "#FFFFFF")
        start = caption["timing"]["start"]
        end = start + caption["timing"]["duration"]
        enable = f"between(t\\,{start}\\,{end})"
        drawtext = (
            f"drawtext=fontfile={fontfile}:"
            f"text='{text}':"
            f"x={x}:y={y}:"
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


def _render_overlay_media(payload: dict, output_path: Path, media_path: Path) -> None:
    element = payload["element"]
    width = payload["video"]["size"]["width"]
    height = payload["video"]["size"]["height"]
    fps = payload["video"].get("fps", 30)
    bg_color = _color_hex(payload["video"].get("bg_color", [0, 0, 0]))
    duration = float(element["timing"]["duration"])
    x = element.get("transform", {}).get("x", 0)
    y = element.get("transform", {}).get("y", 0)

    filters = f"[1:v]scale=iw:ih[ov];[0:v][ov]overlay={x}:{y}"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
        "-i",
        str(media_path),
        "-filter_complex",
        filters,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def _render_audio(payload: dict, output_path: Path, audio_path: Path) -> None:
    element = payload["element"]
    width = payload["video"]["size"]["width"]
    height = payload["video"]["size"]["height"]
    fps = payload["video"].get("fps", 30)
    bg_color = _color_hex(payload["video"].get("bg_color", [0, 0, 0]))
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
        f"[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS,volume={volume}[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
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

    element = payload["element"]
    element_type = element["type"]

    output_path = Path(payload["video"]["output_path"])
    _ensure_output_dir(output_path)

    if element_type == "caption":
        _render_caption_words(payload, output_path)
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
            _render_overlay_media(payload, output_path, media_path)
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
            _render_overlay_media(payload, output_path, media_path)
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
            _render_overlay_media(payload, output_path, media_path)
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
                _render_overlay_media(payload, output_path, media_path)
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
            _render_audio(payload, output_path, media_path)
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
            _render_audio(payload, output_path, media_path)
        elif strict:
            raise FileNotFoundError(media_path)
        return output_path

    raise ValueError(f"Unknown element type: {element_type}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", help="Path to the element input JSON.")
    parser.add_argument("--strict", action="store_true", help="Fail if media is missing.")
    args = parser.parse_args()

    render_from_json(args.input_json, strict=args.strict)


if __name__ == "__main__":
    main()
