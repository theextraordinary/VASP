from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Dict


def crop_video_and_extract_audio(
    *,
    input_video_path: str | Path,
    start_sec: float,
    end_sec: float,
    output_video_path: str | Path,
    output_audio_path: str | Path,
) -> Dict[str, str]:
    """Crop a source video between [start_sec, end_sec] and extract its audio.

    Args:
        input_video_path: Source video file path.
        start_sec: Clip start time in seconds (>= 0).
        end_sec: Clip end time in seconds (> start_sec).
        output_video_path: Output clipped video file path.
        output_audio_path: Output extracted audio file path.

    Returns:
        Dict with normalized output paths: {"video_path": ..., "audio_path": ...}
    """
    source = Path(input_video_path)
    out_video = Path(output_video_path)
    out_audio = Path(output_audio_path)

    if not source.exists():
        raise FileNotFoundError(f"Input video not found: {source}")
    if start_sec < 0:
        raise ValueError("start_sec must be >= 0")
    if end_sec <= start_sec:
        raise ValueError("end_sec must be > start_sec")

    out_video.parent.mkdir(parents=True, exist_ok=True)
    out_audio.parent.mkdir(parents=True, exist_ok=True)

    duration = end_sec - start_sec

    # 1) Crop video segment.
    crop_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(out_video),
    ]
    subprocess.run(crop_cmd, check=True, capture_output=True, text=True)

    # 2) Extract audio from cropped segment.
    audio_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(out_video),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out_audio),
    ]
    subprocess.run(audio_cmd, check=True, capture_output=True, text=True)

    return {
        "video_path": str(out_video).replace("\\", "/"),
        "audio_path": str(out_audio).replace("\\", "/"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crop a video between start/end seconds and extract audio from the clipped video."
    )
    parser.add_argument("--input-video", required=True, help="Path to source video.")
    parser.add_argument("--start-sec", required=True, type=float, help="Clip start time in seconds.")
    parser.add_argument("--end-sec", required=True, type=float, help="Clip end time in seconds.")
    parser.add_argument("--output-video", required=True, help="Path for clipped output video.")
    parser.add_argument("--output-audio", required=True, help="Path for extracted output audio.")
    args = parser.parse_args()

    result = crop_video_and_extract_audio(
        input_video_path=args.input_video,
        start_sec=args.start_sec,
        end_sec=args.end_sec,
        output_video_path=args.output_video,
        output_audio_path=args.output_audio,
    )
    print(result)


if __name__ == "__main__":
    main()
