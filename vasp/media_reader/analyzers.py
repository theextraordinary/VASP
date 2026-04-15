from __future__ import annotations

from pathlib import Path

from vasp.media_reader.schemas import MediaAnalysis


def analyze_video_basic(path: str) -> MediaAnalysis:
    """Placeholder hook for video analysis."""
    name = Path(path).stem
    return MediaAnalysis(summary=f"Video clip: {name}", media_tags=["video"])


def analyze_audio_basic(path: str) -> MediaAnalysis:
    """Placeholder hook for audio analysis."""
    name = Path(path).stem
    return MediaAnalysis(summary=f"Audio track: {name}", media_tags=["audio"])


def analyze_image_basic(path: str) -> MediaAnalysis:
    """Placeholder hook for image analysis."""
    name = Path(path).stem
    return MediaAnalysis(summary=f"Image asset: {name}", media_tags=["image"])
