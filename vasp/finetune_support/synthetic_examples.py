from __future__ import annotations

from vasp.finetune_support.json_schemas import A2VEditPlan, Decision, DecisionType, TrainingExample


def build_bootstrap_examples() -> list[TrainingExample]:
    examples: list[TrainingExample] = []

    ex1_input = {
        "task": {"type": "a2v_edit_plan"},
        "timeline": {"duration_s": 12.0, "fps": 30},
        "media": [{"id": "video_main", "type": "video"}],
        "transcript": {
            "words": [
                {"word": "Today", "start": 0.2, "end": 0.6},
                {"word": "we", "start": 0.7, "end": 0.8},
                {"word": "learn", "start": 0.9, "end": 1.3},
                {"word": "history", "start": 1.4, "end": 1.9},
            ]
        },
    }
    ex1_plan = A2VEditPlan(
        id="plan_hist_001",
        decisions=[
            Decision(
                id="d1",
                type=DecisionType.CAPTION,
                start=0.2,
                duration=1.8,
                target_element_id="caption_track_1",
                payload={"text": "Today we learn history", "max_words": 5, "style": "clean"},
            ),
            Decision(
                id="d2",
                type=DecisionType.EMPHASIS,
                start=0.9,
                duration=1.0,
                target_element_id="caption_track_1",
                payload={"words": ["learn", "history"], "reason": "topic_focus"},
            ),
        ],
    )
    examples.append(TrainingExample(input_payload=ex1_input, output_plan=ex1_plan, tags=["caption", "emphasis"]))

    ex2_input = {
        "task": {"type": "a2v_edit_plan"},
        "timeline": {"duration_s": 20.0, "fps": 30},
        "media": [{"id": "talking_head", "type": "video"}],
        "transcript": {
            "segments": [
                {"text": "This date changed Rome forever", "start": 2.0, "end": 4.8},
                {"text": "Remember the ides of march", "start": 4.9, "end": 7.2},
            ]
        },
    }
    ex2_plan = A2VEditPlan(
        id="plan_hist_002",
        decisions=[
            Decision(
                id="d1",
                type=DecisionType.CAPTION,
                start=2.0,
                duration=2.8,
                target_element_id="caption_track_1",
                payload={"text": "This date changed Rome forever", "max_words": 6, "style": "bold"},
            ),
            Decision(
                id="d2",
                type=DecisionType.ZOOM,
                start=4.9,
                duration=2.0,
                target_element_id="talking_head",
                payload={"level": 1.12, "anchor": "center"},
            ),
            Decision(
                id="d3",
                type=DecisionType.CAPTION,
                start=4.9,
                duration=2.3,
                target_element_id="caption_track_1",
                payload={"text": "Remember the ides of march", "max_words": 6, "style": "clean"},
            ),
        ],
    )
    examples.append(TrainingExample(input_payload=ex2_input, output_plan=ex2_plan, tags=["zoom", "caption"]))

    ex3_input = {
        "task": {"type": "a2v_edit_plan"},
        "timeline": {"duration_s": 15.0, "fps": 30},
        "media": [{"id": "voice_track", "type": "audio"}],
        "transcript": {"text": "Breaking story in three points"},
    }
    ex3_plan = A2VEditPlan(
        id="plan_news_001",
        decisions=[
            Decision(
                id="d1",
                type=DecisionType.CUT,
                start=0.0,
                duration=0.1,
                target_element_id=None,
                payload={"reason": "hook_start"},
            ),
            Decision(
                id="d2",
                type=DecisionType.OVERLAY,
                start=0.1,
                duration=2.0,
                target_element_id="overlay_track",
                payload={"overlay_type": "title_card", "uri": None, "opacity": 1.0},
            ),
            Decision(
                id="d3",
                type=DecisionType.SFX,
                start=0.0,
                duration=0.6,
                target_element_id="sfx_track",
                payload={"name": "whoosh", "gain_db": -3},
            ),
        ],
    )
    examples.append(TrainingExample(input_payload=ex3_input, output_plan=ex3_plan, tags=["overlay", "sfx"]))

    return examples
