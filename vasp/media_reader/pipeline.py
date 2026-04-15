from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from vasp.a2v.transcription import transcribe_media_with_features
from vasp.core.serialization import serialize_element_json
from vasp.media_reader.analyzers import analyze_audio_basic, analyze_image_basic, analyze_video_basic
from vasp.media_reader.builder import build_intermediate_payload
from vasp.media_reader.probe import probe_media
from vasp.media_reader.schemas import MediaAnalysis, MediaContext, MediaInput, MediaProbeInfo, UserEditIntent


def detect_media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".mp4", ".mov", ".mkv", ".avi"}:
        return "video"
    if suffix in {".gif"}:
        return "gif"
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"
    if suffix in {".mp3", ".wav", ".m4a", ".aac"}:
        return "audio"
    return "video"


def generate_input_json(
    *,
    instruction: str,
    media_paths: list[Any],
    output_path: Optional[str] = None,
    options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create a serializer-ready input JSON from user instruction and media."""
    opts = options or {}
    intent = UserEditIntent(instruction=instruction, **_intent_options(opts))
    asr_enabled = bool(opts.get("asr_enabled", True))
    asr_model_size = str(opts.get("asr_model_size", "small"))
    inputs: list[MediaInput] = []
    probe_map: dict[str, MediaProbeInfo] = {}
    analysis_map: dict[str, MediaAnalysis] = {}

    normalized_media = _normalize_media_items(media_paths)
    for idx, media_item in enumerate(normalized_media, start=1):
        path = media_item["path"]
        media_type = detect_media_type(path)
        media_id = f"media_{idx}"
        inputs.append(
            MediaInput(
                id=media_id,
                path=path,
                media_type=media_type,
                aim=media_item.get("aim"),
                about=media_item.get("about"),
            )
        )

        probe = probe_media(path)
        probe_map[media_id] = probe

        if media_type == "video":
            analysis = analyze_video_basic(path)
            if asr_enabled:
                transcript = transcribe_media_with_features(path, model_size=asr_model_size)
                analysis.transcript = transcript
                warnings = list((transcript.get("word_stats") or {}).get("warnings", []))
                if warnings:
                    analysis.warnings.extend(warnings)
            analysis_map[media_id] = analysis
        elif media_type in ("audio", "music", "sfx"):
            analysis = analyze_audio_basic(path)
            if asr_enabled:
                transcript = transcribe_media_with_features(path, model_size=asr_model_size)
                analysis.transcript = transcript
                warnings = list((transcript.get("word_stats") or {}).get("warnings", []))
                if warnings:
                    analysis.warnings.extend(warnings)
            analysis_map[media_id] = analysis
        else:
            analysis_map[media_id] = analyze_image_basic(path)

    payload = build_intermediate_payload(
        intent=intent,
        inputs=inputs,
        probe_map=probe_map,
        analysis_map=analysis_map,
        output_path=output_path,
        options=opts,
    )
    return payload.model_dump()


def build_serialized_bundle(
    *,
    instruction: str,
    media_paths: list[Any],
    output_path: Optional[str] = None,
    options: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Integration helper: media reader -> serializer bundle."""
    payload = generate_input_json(
        instruction=instruction,
        media_paths=media_paths,
        output_path=output_path,
        options=options,
    )
    return serialize_element_json(payload)


def _intent_options(options: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "style",
        "tone",
        "notes",
        "target_aspect_ratio",
        "caption_enabled",
        "zoom_style",
        "meme_style",
    }
    return {k: v for k, v in options.items() if k in allowed}


def _normalize_media_items(media_paths: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in media_paths:
        if isinstance(item, str):
            out.append({"path": item, "aim": None, "about": None})
            continue
        if isinstance(item, (tuple, list)) and len(item) >= 1:
            path = str(item[0])
            aim = str(item[1]).strip() if len(item) > 1 and item[1] is not None else None
            about = str(item[2]).strip() if len(item) > 2 and item[2] is not None else None
            out.append({"path": path, "aim": aim or None, "about": about or None})
            continue
        if isinstance(item, dict):
            path = str(item.get("path", "")).strip()
            if not path:
                continue
            aim = item.get("aim")
            about = item.get("about")
            out.append(
                {
                    "path": path,
                    "aim": str(aim).strip() if aim is not None and str(aim).strip() else None,
                    "about": str(about).strip() if about is not None and str(about).strip() else None,
                }
            )
            continue
        raise ValueError(f"Unsupported media input item: {item!r}")
    return out
