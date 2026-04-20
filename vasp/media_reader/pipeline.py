from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import json

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
    asr_only_first_input = bool(opts.get("asr_only_first_input", False))
    asr_model_size = str(opts.get("asr_model_size", "small"))
    caption_pause_threshold = float(opts.get("caption_group_pause_threshold_s", 0.35))
    caption_max_words = int(opts.get("caption_group_max_words", 5))
    caption_max_group_span_s = float(opts.get("caption_group_max_span_s", 2.0))
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

        do_asr = asr_enabled and (not asr_only_first_input or idx == 1)

        if media_type == "video":
            analysis = analyze_video_basic(path)
            if do_asr:
                transcript = transcribe_media_with_features(path, model_size=asr_model_size)
                transcript = _hydrate_transcript_from_sidecar(path, transcript)
                transcript = _group_transcript_words(
                    transcript,
                    pause_threshold_s=caption_pause_threshold,
                    max_words=caption_max_words,
                    max_group_span_s=caption_max_group_span_s,
                )
                analysis.transcript = transcript
                warnings = list((transcript.get("word_stats") or {}).get("warnings", []))
                if warnings:
                    analysis.warnings.extend(warnings)
            analysis_map[media_id] = analysis
        elif media_type in ("audio", "music", "sfx"):
            analysis = analyze_audio_basic(path)
            if do_asr:
                transcript = transcribe_media_with_features(path, model_size=asr_model_size)
                transcript = _hydrate_transcript_from_sidecar(path, transcript)
                transcript = _group_transcript_words(
                    transcript,
                    pause_threshold_s=caption_pause_threshold,
                    max_words=caption_max_words,
                    max_group_span_s=caption_max_group_span_s,
                )
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
    payload_dict = payload.model_dump()
    if bool(opts.get("emit_word_timing_files", True)):
        out_dir = opts.get("word_timing_output_dir") or "output/word_timing_maps"
        _write_word_timing_outputs(payload_dict, out_dir)
    return payload_dict


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


def _group_transcript_words(
    transcript: dict[str, Any],
    *,
    pause_threshold_s: float,
    max_words: int,
    max_group_span_s: float,
) -> dict[str, Any]:
    """Convert transcript words into deterministic caption groups.

    media.json will carry grouped caption timing in transcript['caption_groups'].
    To avoid duplicated representations, transcript['words'] is replaced with [].
    """
    if not isinstance(transcript, dict):
        return transcript
    words = transcript.get("words")
    if not isinstance(words, list) or not words:
        return transcript

    # sanitize
    norm_words: list[dict[str, Any]] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        try:
            start = float(w.get("start"))
        except Exception:
            continue
        try:
            end = float(w.get("end"))
        except Exception:
            end = start
        if end < start:
            end = start
        norm_words.append({"text": text, "start": start, "end": end})
    if not norm_words:
        return transcript

    def _ends_sentence(tok: str) -> bool:
        t = (tok or "").strip()
        return t.endswith(".") or t.endswith("!") or t.endswith("?")

    def _starts_upper(tok: str) -> bool:
        t = (tok or "").strip()
        return bool(t) and t[0].isalpha() and t[0].isupper()

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    group_start = 0.0
    for i, w in enumerate(norm_words):
        if not current:
            group_start = float(w["start"])
        current.append(w)
        if i == len(norm_words) - 1:
            groups.append(current)
            break
        nxt = norm_words[i + 1]
        gap = float(nxt["start"]) - float(w["end"])
        next_span = float(nxt["start"]) - group_start

        split = False
        if _ends_sentence(str(w.get("text", ""))):
            split = True
        if _starts_upper(str(nxt.get("text", ""))):
            split = True
        if gap >= pause_threshold_s:
            split = True
        if len(current) >= max(1, max_words):
            split = True
        if next_span > max_group_span_s:
            split = True
        if split:
            groups.append(current)
            current = []

    caption_groups: list[dict[str, Any]] = []
    word_timing_map: list[dict[str, Any]] = []
    for i, g in enumerate(groups):
        start = float(g[0]["start"])
        end = float(groups[i + 1][0]["start"]) if i < len(groups) - 1 else float(g[-1]["end"])
        caption_groups.append(
            {
                "group_id": f"group_{i+1}",
                "text": " ".join(str(x.get("text", "")).strip() for x in g).strip(),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(max(0.0, end - start), 3),
                "word_count": len(g),
            }
        )
    for w in norm_words:
        word_timing_map.append(
            {
                "text": str(w["text"]),
                "start": round(float(w["start"]), 3),
                "end": round(float(w["end"]), 3),
            }
        )

    out = dict(transcript)
    out["caption_groups"] = caption_groups
    out["word_timing_map"] = word_timing_map
    out["grouping_config"] = {
        "pause_threshold_s": pause_threshold_s,
        "max_words": max_words,
        "max_group_span_s": max_group_span_s,
        "algorithm": "punctuation|uppercase-next|pause|max_words|max_group_span",
    }
    # requested: grouped captions instead of words in media.json
    out["words"] = []
    return out


def _hydrate_transcript_from_sidecar(path: str, transcript: dict[str, Any]) -> dict[str, Any]:
    """Fallback when whisperx is unavailable: read `<media>_whisper.json` if present."""
    if not isinstance(transcript, dict):
        transcript = {}
    words = transcript.get("words")
    if isinstance(words, list) and words:
        return transcript

    p = Path(path)
    sidecar = p.with_name(f"{p.stem}_whisper.json")
    if not sidecar.exists():
        return transcript
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return transcript
    if not isinstance(data, list):
        return transcript

    norm_words: list[dict[str, Any]] = []
    for w in data:
        if not isinstance(w, dict):
            continue
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        try:
            start = float(w.get("start"))
        except Exception:
            continue
        try:
            end = float(w.get("end"))
        except Exception:
            end = start
        if end < start:
            end = start
        norm_words.append({"text": text, "start": start, "end": end})
    if not norm_words:
        return transcript

    out = dict(transcript)
    out["words"] = norm_words
    out["full_text"] = " ".join(x["text"] for x in norm_words).strip()
    out["language"] = out.get("language") or "en"
    out["segments"] = out.get("segments") or []
    stats = out.get("word_stats") if isinstance(out.get("word_stats"), dict) else {}
    stats = dict(stats)
    stats["word_count"] = len(norm_words)
    warnings = [w for w in (stats.get("warnings") or []) if w != "whisperx_unavailable"]
    stats["warnings"] = warnings
    out["word_stats"] = stats
    return out


def _write_word_timing_outputs(payload: dict[str, Any], output_dir: str | Path) -> None:
    """Write per-media and combined word timing maps as separate files."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    media_ctx = payload.get("media_context") if isinstance(payload, dict) else {}
    analysis = (media_ctx or {}).get("analysis") if isinstance(media_ctx, dict) else {}
    combined: dict[str, list[dict[str, Any]]] = {}

    if not isinstance(analysis, dict):
        return
    for media_id, row in analysis.items():
        if not isinstance(row, dict):
            continue
        transcript = row.get("transcript")
        if not isinstance(transcript, dict):
            continue
        mapping = transcript.get("word_timing_map")
        if not isinstance(mapping, list):
            words = transcript.get("words")
            if isinstance(words, list):
                mapping = words
            else:
                mapping = []
        clean: list[dict[str, Any]] = []
        for item in mapping:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            try:
                start = float(item.get("start"))
                end = float(item.get("end"))
            except Exception:
                continue
            if end < start:
                end = start
            clean.append({"text": text, "start": round(start, 3), "end": round(end, 3)})
        combined[str(media_id)] = clean
        (out_dir / f"{media_id}_word_timing_map.json").write_text(
            json.dumps(clean, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (out_dir / "word_timing_map_all.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
