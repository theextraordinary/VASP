from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from vasp.media_reader.schemas import MediaProbeInfo


def _ffprobe_available() -> bool:
    try:
        subprocess.run(["ffprobe", "-version"], check=False, capture_output=True, text=True)
        return True
    except FileNotFoundError:
        return False


def probe_media(path: str) -> MediaProbeInfo:
    """Probe a media file using ffprobe when available."""
    media_path = Path(path)
    if not media_path.exists():
        return MediaProbeInfo()
    if not _ffprobe_available():
        return MediaProbeInfo()

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(media_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        return MediaProbeInfo()

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return MediaProbeInfo()

    return _parse_probe_payload(payload)


def _parse_probe_payload(payload: dict) -> MediaProbeInfo:
    streams = payload.get("streams", [])
    fmt = payload.get("format", {})

    duration = _safe_float(fmt.get("duration"))
    width, height, fps = _video_stream_meta(streams)
    audio_channels, sample_rate = _audio_stream_meta(streams)

    return MediaProbeInfo(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        audio_channels=audio_channels,
        sample_rate=sample_rate,
    )


def _video_stream_meta(streams: list[dict]) -> tuple[Optional[int], Optional[int], Optional[float]]:
    for stream in streams:
        if stream.get("codec_type") == "video":
            width = _safe_int(stream.get("width"))
            height = _safe_int(stream.get("height"))
            fps = _parse_fps(stream.get("r_frame_rate") or stream.get("avg_frame_rate"))
            return width, height, fps
    return None, None, None


def _audio_stream_meta(streams: list[dict]) -> tuple[Optional[int], Optional[int]]:
    for stream in streams:
        if stream.get("codec_type") == "audio":
            channels = _safe_int(stream.get("channels"))
            sample_rate = _safe_int(stream.get("sample_rate"))
            return channels, sample_rate
    return None, None


def _parse_fps(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(value)
    except ValueError:
        return None


def _safe_float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
