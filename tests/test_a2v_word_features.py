from __future__ import annotations

from vasp.a2v.word_features import enrich_transcript_words


def test_word_enrichment_preserves_timing_and_adds_tags() -> None:
    words = [
        {"text": "Today", "start": 0.1, "end": 0.5},
        {"text": "is", "start": 0.52, "end": 0.62},
        {"text": "15th", "start": 0.64, "end": 0.9},
        {"text": "March.", "start": 0.95, "end": 1.2},
    ]
    enriched, stats = enrich_transcript_words(words)

    assert len(enriched) == 4
    assert enriched[0]["start"] == 0.1
    assert enriched[3]["end"] == 1.2
    assert "importance_score" in enriched[0]
    assert "sentence_id" in enriched[0]
    assert "group_id" in enriched[0]
    assert stats["word_count"] == 4


def test_word_enrichment_marks_numeric_and_date_hints() -> None:
    words = [
        {"text": "On", "start": 0.0, "end": 0.1},
        {"text": "15th", "start": 0.2, "end": 0.4},
        {"text": "March", "start": 0.5, "end": 0.8},
    ]
    enriched, _ = enrich_transcript_words(words)
    assert enriched[1]["is_numeric"] is True
    assert enriched[1]["is_date_hint"] is True
    assert enriched[2]["is_date_hint"] is True
