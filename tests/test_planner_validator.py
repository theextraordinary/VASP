from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vasp.planner.planner_validator import (
    parse_planner_json,
    validate_and_fix_planner_output,
    validate_planner_output,
)


def _grouped() -> list[dict]:
    return [
        {"index": 0, "text": "hello", "start": 0.1, "end": 0.5},
        {"index": 1, "text": "world", "start": 0.5, "end": 1.0},
        {"index": 2, "text": "again", "start": 1.0, "end": 1.5},
    ]


def _assets() -> dict:
    return {
        "media_1": {"type": "audio"},
        "media_2": {"type": "video"},
        "media_3": {"type": "gif"},
        "caption_track_1": {"type": "caption"},
    }


def _base_planner() -> dict:
    return {
        "video_summary": {"theme": "x", "mood": "y", "main_audio": "media_1", "main_caption": "caption_track_1"},
        "asset_understanding": [
            {"element_id": "media_1", "suggested_role": "main_audio"},
            {"element_id": "media_2", "suggested_role": "supporting_visual"},
            {"element_id": "media_3", "suggested_role": "accent"},
            {"element_id": "caption_track_1"},
        ],
        "segments": [
            {
                "segment_id": "seg_001",
                "t_start": 0.1,
                "t_end": 1.0,
                "caption_indices": [0, 1],
                "spoken_text": "hello world",
                "segment_purpose": "p",
                "visual_candidates": [
                    {
                        "element_id": "media_2",
                        "role": "supporting_visual",
                        "time_hint": {"start": 0.1, "end": 1.0},
                    }
                ],
                "caption_instruction": "c",
                "transition_intent": "cut",
            },
            {
                "segment_id": "seg_002",
                "t_start": 1.0,
                "t_end": 1.5,
                "caption_indices": [2],
                "spoken_text": "again",
                "segment_purpose": "p2",
                "visual_candidates": [],
                "caption_instruction": "c2",
                "transition_intent": "fade",
            },
        ],
    }


def test_valid_planner_output_passes() -> None:
    planner = _base_planner()
    errors = validate_planner_output(planner, _grouped(), _assets())
    assert errors == []


def test_audio_removed_from_visual_candidates() -> None:
    planner = _base_planner()
    planner["segments"][0]["visual_candidates"].append(
        {"element_id": "media_1", "role": "supporting_visual", "time_hint": {"start": 0.1, "end": 0.5}}
    )
    fixed, _ = validate_and_fix_planner_output(planner, _grouped(), _assets())
    ids = [x["element_id"] for x in fixed["segments"][0]["visual_candidates"]]
    assert "media_1" not in ids


def test_spoken_text_fixed() -> None:
    planner = _base_planner()
    planner["segments"][0]["spoken_text"] = "wrong text"
    fixed, _ = validate_and_fix_planner_output(planner, _grouped(), _assets())
    assert fixed["segments"][0]["spoken_text"] == "hello world"


def test_segment_times_fixed() -> None:
    planner = _base_planner()
    planner["segments"][0]["t_start"] = 0.0
    planner["segments"][0]["t_end"] = 9.9
    fixed, _ = validate_and_fix_planner_output(planner, _grouped(), _assets())
    assert fixed["segments"][0]["t_start"] == 0.1
    assert fixed["segments"][0]["t_end"] == 1.0


def test_missing_caption_index_creates_fallback() -> None:
    planner = _base_planner()
    planner["segments"] = planner["segments"][:1]  # drop index 2 coverage
    fixed, _ = validate_and_fix_planner_output(planner, _grouped(), _assets())
    covered = sorted(i for s in fixed["segments"] for i in s["caption_indices"])
    assert covered == [0, 1, 2]


def test_duplicate_caption_index_removed_from_later_segment() -> None:
    planner = _base_planner()
    planner["segments"][1]["caption_indices"] = [1, 2]
    fixed, _ = validate_and_fix_planner_output(planner, _grouped(), _assets())
    covered = [i for s in fixed["segments"] for i in s["caption_indices"]]
    assert covered.count(1) == 1


def test_invalid_time_hint_snapped_or_removed() -> None:
    planner = _base_planner()
    planner["segments"][0]["visual_candidates"][0]["time_hint"] = {"start": 0.33, "end": 0.88}
    fixed, _ = validate_and_fix_planner_output(planner, _grouped(), _assets())
    vc = fixed["segments"][0]["visual_candidates"]
    assert vc
    assert vc[0]["time_hint"] == {"start": 0.5, "end": 1.0}


def test_truncated_json_raises_clear_error() -> None:
    with pytest.raises(ValueError):
        parse_planner_json('{"video_summary": {"theme": "x"')
