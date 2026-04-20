from __future__ import annotations

import re
from typing import Any


_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "it",
    "this",
    "that",
    "you",
    "we",
    "i",
    "they",
    "he",
    "she",
}

_MONTHS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}

_PUNCT_HEAVY = {".", ",", "!", "?", ":", ";"}
_ENTITY_HINTS = {"ai", "gpt", "gemma", "openai", "google", "youtube", "tiktok"}


def enrich_transcript_words(words: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach deterministic rich tags to timed words."""
    if not words:
        return [], {"word_count": 0, "important_count": 0, "avg_pause_s": 0.0, "warnings": []}

    enriched: list[dict[str, Any]] = []
    pauses: list[float] = []
    important_count = 0
    sentence_id = 0
    group_id = 0
    prev_end = None

    for idx, raw in enumerate(words):
        text = str(raw.get("text") or raw.get("word") or "").strip()
        start = _to_float(raw.get("start"), default=0.0)
        end = _to_float(raw.get("end"), default=start)
        if end < start:
            end = start
        clean = _strip_token(text)
        lower = clean.lower()

        pause_before = 0.0 if prev_end is None else max(0.0, start - prev_end)
        next_start = _to_float(words[idx + 1].get("start"), default=end) if idx + 1 < len(words) else end
        pause_after = max(0.0, next_start - end)
        pauses.append(pause_before)

        if pause_before >= 0.7 and idx > 0:
            group_id += 1
        if _ends_sentence(text) and idx > 0:
            sentence_id += 1

        duration = max(0.001, end - start)
        is_stopword = lower in _STOPWORDS
        is_numeric = bool(re.fullmatch(r"\d+([.,:/-]\d+)*", lower))
        punctuation_class = "heavy" if any(p in text for p in _PUNCT_HEAVY) else "light"
        speaking_rate = _speaking_rate_bucket(text=text, duration=duration)

        is_date_hint = lower in _MONTHS or bool(re.fullmatch(r"\d{1,2}(st|nd|rd|th)?", lower))
        is_entity_hint = lower in _ENTITY_HINTS or (clean[:1].isupper() and len(clean) > 1)

        importance_score = 0.0
        importance_score += 0.22 if not is_stopword else 0.0
        importance_score += 0.20 if is_numeric or is_date_hint else 0.0
        importance_score += 0.20 if is_entity_hint else 0.0
        importance_score += 0.15 if punctuation_class == "heavy" else 0.0
        importance_score += 0.23 if pause_after >= 0.35 else 0.0
        importance_score = min(1.0, round(importance_score, 3))

        if importance_score >= 0.65:
            importance_label = "high"
            important = True
            important_count += 1
        elif importance_score >= 0.35:
            importance_label = "medium"
            important = False
        else:
            importance_label = "low"
            important = False

        enriched.append(
            {
                "text": text,
                "start": round(start, 3),
                "end": round(end, 3),
                "pause_before": round(pause_before, 3),
                "pause_after": round(pause_after, 3),
                "sentence_id": sentence_id,
                "group_id": group_id,
                "is_stopword": is_stopword,
                "is_numeric": is_numeric,
                "punctuation_class": punctuation_class,
                "speaking_rate_bucket": speaking_rate,
                "is_date_hint": is_date_hint,
                "is_entity_hint": is_entity_hint,
                "importance_score": importance_score,
                "importance_label": importance_label,
                "important": important,
            }
        )
        prev_end = end

    avg_pause = sum(pauses) / len(pauses) if pauses else 0.0
    stats = {
        "word_count": len(enriched),
        "important_count": important_count,
        "avg_pause_s": round(avg_pause, 4),
        "warnings": [],
    }
    return enriched, stats


def _speaking_rate_bucket(*, text: str, duration: float) -> str:
    cps = len(text.strip()) / max(0.001, duration)
    if cps < 8:
        return "slow"
    if cps < 16:
        return "medium"
    return "fast"


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?"))


def _strip_token(text: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", text or "")


def _to_float(value: Any, *, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

