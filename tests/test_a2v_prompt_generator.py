from __future__ import annotations

from vasp.a2v.prompt_generator import a2v_prompt_generator


def test_a2v_prompt_generator_contains_instruction_bundle_and_transcript() -> None:
    prompt = a2v_prompt_generator(
        instruction="main",
        instruction_1="one",
        instruction_2="two",
        instruction_3="three",
        media_json={
            "media_context": {
                "analysis": {
                    "media_1": {
                        "transcript": {
                            "full_text": "hello world",
                            "words": [{"text": "hello", "start": 0.0, "end": 0.3}],
                            "language": "en",
                            "word_stats": {"important_count": 1, "avg_pause_s": 0.1},
                        }
                    }
                }
            }
        },
        elements_json={"elements": [{"element_id": "caption_1", "timing": {"start": 0.0, "duration": 1.0}, "actions": []}]},
        element_props_json={"elements": [{"element_id": "caption_1", "properties": {"type": "caption", "timing": {"start": 0.0, "duration": 1.0}, "transform": {"x": 10, "y": 20}}}]},
    )
    assert "main" in prompt
    assert "one" in prompt
    assert "hello world" in prompt
    assert "caption_1" in prompt
