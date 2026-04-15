from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from vasp.media_reader.schemas import (
    IntermediateInputPayload,
    MediaAnalysis,
    MediaContext,
    MediaInput,
    MediaProbeInfo,
    UserEditIntent,
)


def build_intermediate_payload(
    *,
    intent: UserEditIntent,
    inputs: list[MediaInput],
    probe_map: dict[str, MediaProbeInfo],
    analysis_map: dict[str, MediaAnalysis],
    output_path: Optional[str],
    options: Optional[dict[str, Any]],
) -> IntermediateInputPayload:
    """Construct a serializer-ready payload with minimal defaults."""
    opts = options or {}
    # Keep a consistent mobile-first canvas across generated outputs.
    width = 1080
    height = 1920
    fps = int(opts.get("fps", 30))
    target_duration = float(opts.get("target_duration_s", 60.0))

    elements: list[dict[str, Any]] = []

    for idx, media in enumerate(inputs, start=1):
        probe = probe_map.get(media.id, MediaProbeInfo())
        source_duration = probe.duration or float(opts.get("default_duration", 5.0))
        duration = target_duration
        element_id = f"{media.media_type}_{idx}"

        if media.media_type in ("video", "gif", "image"):
            elements.append(
                {
                    "id": element_id,
                    "type": "video" if media.media_type == "video" else media.media_type,
                    "source_uri": media.path,
                    "length": source_duration,
                    "aim": media.aim,
                    "about": media.about,
                    "transform": {"x": width / 2, "y": height / 2},
                    "metadata": {"media_id": media.id, "aim": media.aim, "about": media.about},
                    "actions": [{"t_start": 0.0, "t_end": duration, "op": "show", "params": {}}],
                }
            )
        elif media.media_type in ("audio", "music", "sfx"):
            elements.append(
                {
                    "id": element_id,
                    "type": "music" if media.media_type in ("audio", "music") else "sfx",
                    "source_uri": media.path,
                    "length": source_duration,
                    "aim": media.aim,
                    "about": media.about,
                    "metadata": {"media_id": media.id, "aim": media.aim, "about": media.about},
                    "actions": [{"t_start": 0.0, "t_end": duration, "op": "play", "params": {}}],
                }
            )

    # Seed fallback caption elements only when ASR words are not available.
    # If transcript words exist, serializer/A2V grouping will create caption-group elements.
    has_asr_words = _has_transcript_words(analysis_map)
    asr_requested = bool(opts.get("asr_enabled", False))
    should_seed_fallback = intent.caption_enabled and not has_asr_words and not asr_requested
    if should_seed_fallback:
        for idx, block in enumerate(_default_ai_caption_blocks(target_duration), start=1):
            elements.append(
                {
                    "id": f"caption_{idx}",
                    "type": "caption",
                    "text": block["text"],
                    "transform": {"x": width / 2, "y": block["y"]},
                    "actions": [{"t_start": block["t_start"], "t_end": block["t_end"], "op": "show", "params": {}}],
                }
            )

    video_block = {
        "size": {"width": width, "height": height},
        "fps": fps,
        "bg_color": opts.get("bg_color", [0, 0, 0]),
        "output_path": output_path or str(Path("output") / "media_reader_output.mp4"),
    }

    media_context = MediaContext(inputs=inputs, probe=probe_map, analysis=analysis_map)
    return IntermediateInputPayload(
        intent=intent,
        media_context=media_context,
        video=video_block,
        elements=elements,
    )


def _has_transcript_words(analysis_map: dict[str, MediaAnalysis]) -> bool:
    for analysis in analysis_map.values():
        transcript = analysis.transcript
        if isinstance(transcript, dict):
            words = transcript.get("words", [])
            if isinstance(words, list) and len(words) > 0:
                return True
    return False


def _default_ai_caption_blocks(target_duration: float) -> list[dict[str, Any]]:
    lines = [
        "AI is changing how we create.",
        "Ideas to visuals in seconds.",
        "Code, design, and motion together.",
        "From prompt to polished reel.",
        "Build faster, iterate smarter.",
        "This is the future of storytelling.",
    ]
    if target_duration <= 0:
        return []
    block = target_duration / max(1, len(lines))
    out: list[dict[str, Any]] = []
    for i, text in enumerate(lines):
        start = round(i * block, 3)
        end = round(min(target_duration, (i + 1) * block), 3)
        out.append(
            {
                "text": text,
                "t_start": start,
                "t_end": end,
                "y": 1600 if i % 2 == 0 else 320,
            }
        )
    return out
