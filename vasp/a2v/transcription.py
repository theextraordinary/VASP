from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from vasp.a2v.word_features import enrich_transcript_words


def transcribe_with_whisperx(
    media_path: str,
    *,
    model_size: str = "small",
    language: Optional[str] = None,
) -> dict[str, Any]:
    """Run WhisperX transcription with safe fallback when dependency/runtime is unavailable."""
    path = Path(media_path)
    if not path.exists():
        return _empty_transcript(warning=f"media_not_found:{media_path}")

    try:
        import whisperx  # type: ignore[import-not-found]
    except Exception:
        return _empty_transcript(warning="whisperx_unavailable")

    try:
        if _is_video_file(path) and not _has_audio_stream(path):
            return _empty_transcript(warning="no_audio_stream")

        # CPU default keeps behavior predictable across environments.
        device = "cpu"
        model = whisperx.load_model(model_size, device=device, language=language)
        result = model.transcribe(str(path))

        # Force alignment pass so word boundaries match actual spoken regions
        # more accurately (and preserve real pauses between neighboring words).
        try:
            detected_lang = (result or {}).get("language") or language
            if detected_lang and (result or {}).get("segments"):
                align_model, metadata = whisperx.load_align_model(language_code=detected_lang, device=device)
                aligned = whisperx.align(
                    result["segments"],
                    align_model,
                    metadata,
                    str(path),
                    device,
                    return_char_alignments=False,
                )
                if isinstance(aligned, dict) and aligned.get("segments"):
                    result = aligned
        except Exception:
            # Keep robust fallback to raw WhisperX word output if align model
            # is unavailable for this language/runtime.
            pass
    except Exception as exc:
        msg = str(exc).replace("\r", " ").replace("\n", " ").strip()
        if len(msg) > 240:
            msg = msg[:240] + "..."
        return _empty_transcript(warning=f"whisperx_failed:{msg}")

    words = _extract_words(result)
    segments = _extract_segments(result)
    full_text = _extract_text(result, segments, words)
    lang = (result or {}).get("language") or language
    enriched_words, word_stats = enrich_transcript_words(words)

    return {
        "full_text": full_text,
        "words": enriched_words,
        "segments": segments,
        "language": lang,
        "word_stats": word_stats,
    }


def transcribe_media_with_features(
    media_path: str,
    *,
    model_size: str = "small",
    language: Optional[str] = None,
) -> dict[str, Any]:
    """Public helper used by Media Reader to obtain enriched transcript payload."""
    return transcribe_with_whisperx(media_path, model_size=model_size, language=language)


def _empty_transcript(*, warning: str) -> dict[str, Any]:
    return {
        "full_text": "",
        "words": [],
        "segments": [],
        "language": None,
        "word_stats": {"word_count": 0, "important_count": 0, "warnings": [warning]},
    }


def _extract_words(result: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for seg in (result or {}).get("segments", []) or []:
        seg_words = seg.get("words", []) or []
        if seg_words:
            for w in seg_words:
                text = str(w.get("word") or w.get("text") or "").strip()
                if not text:
                    continue
                start = _safe_float(w.get("start"))
                end = _safe_float(w.get("end"))
                words.append(
                    {
                        "text": text,
                        "start": 0.0 if start is None else start,
                        "end": 0.0 if end is None else max(end, start or 0.0),
                    }
                )
            continue

        # Fallback: synthesize word timing from segment-level timestamps.
        seg_text = str(seg.get("text") or "").strip()
        if not seg_text:
            continue
        seg_start = _safe_float(seg.get("start")) or 0.0
        seg_end = _safe_float(seg.get("end")) or seg_start
        tokens = [t for t in seg_text.split() if t.strip()]
        if not tokens:
            continue
        span = max(0.001, seg_end - seg_start)
        step = span / len(tokens)
        for i, text in enumerate(tokens):
            start = seg_start + i * step
            end = seg_start + (i + 1) * step
            words.append(
                {
                    "text": text,
                    "start": start,
                    "end": max(end, start),
                }
            )
    return _normalize_word_boundaries(words)


def _normalize_word_boundaries(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize pathological overlaps/zero-lengths while preserving natural gaps.
    """
    if not words:
        return words

    out: list[dict[str, Any]] = []
    prev_end = 0.0
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        start = _safe_float(w.get("start"))
        end = _safe_float(w.get("end"))
        if start is None:
            start = prev_end
        if end is None:
            end = start

        # Prevent backwards time while keeping genuine silence.
        start = max(start, 0.0)
        end = max(end, start)

        # Clamp minor overlap jitter only (<=40ms). Do not collapse real pauses.
        if start < prev_end:
            if (prev_end - start) <= 0.04:
                start = prev_end
                end = max(end, start)
            else:
                start = prev_end
                end = max(end, start)

        # Ensure tiny audible width for display if model returns identical times.
        if end == start:
            end = start + 0.02

        out.append({"text": text, "start": start, "end": end})
        prev_end = end
    return out


def _extract_segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, seg in enumerate((result or {}).get("segments", []) or []):
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        start = _safe_float(seg.get("start")) or 0.0
        end = _safe_float(seg.get("end"))
        if end is None:
            end = start
        out.append({"id": idx, "start": start, "end": max(end, start), "text": text})
    return out


def _extract_text(result: dict[str, Any], segments: list[dict[str, Any]], words: list[dict[str, Any]]) -> str:
    text = str((result or {}).get("text") or "").strip()
    if text:
        return text
    if segments:
        return " ".join(seg["text"] for seg in segments).strip()
    return " ".join(w["text"] for w in words).strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_video_file(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def _has_audio_stream(path: Path) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-select_streams",
        "a",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except Exception:
        return True
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return True
    streams = payload.get("streams", [])
    return bool(streams)
