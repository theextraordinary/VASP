from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from vasp.render.json_creator import create_renderer_json
from vasp.validation.edit_plan_validator import validate_llm1_output


def _schema() -> dict:
    p = Path("vasp/schemas/element_capability_schema.json")
    return json.loads(p.read_text(encoding="utf-8"))


def _current_state() -> dict:
    return {
        "canvas": {"width": 1080, "height": 1920},
        "duration": 10.0,
        "existing_elements": [
            {"element_id": "audio_1", "element_type": "Music"},
            {"element_id": "caption_1", "element_type": "Caption"},
            {"element_id": "image_1", "element_type": "Image"},
        ],
        "occupied_regions_by_time": [],
    }


def _base_output() -> dict:
    return {
        "edit_decisions": [
            {
                "decision_id": "d1",
                "element_id": "caption_1",
                "element_type": "Caption",
                "action": "show",
                "t_start": 1.0,
                "t_end": 2.0,
                "purpose": "caption",
                "reason": "sync",
                "depends_on": [],
                "avoid_overlap_with": [],
                "placement_zone": "bottom",
                "notes_for_styler": "",
            }
        ],
        "element_property_table": [
            {
                "element_id": "audio_1",
                "element_type": "Music",
                "exists_in_input": True,
                "is_new_element": False,
                "t_start": 0.0,
                "t_end": 10.0,
                "x": None,
                "y": None,
                "width": None,
                "height": None,
                "z_index": 0,
                "role": "audio",
                "must_not_cover": [],
                "can_be_covered_by": [],
                "sync_reference": None,
                "content_reference": None,
                "behavior": "play",
            },
            {
                "element_id": "caption_1",
                "element_type": "Caption",
                "exists_in_input": True,
                "is_new_element": False,
                "t_start": 1.0,
                "t_end": 4.0,
                "x": 80.0,
                "y": 1500.0,
                "width": 920.0,
                "height": 220.0,
                "z_index": 3,
                "role": "caption",
                "must_not_cover": [],
                "can_be_covered_by": [],
                "sync_reference": "audio_1",
                "content_reference": "hello world",
                "behavior": "show",
            },
            {
                "element_id": "image_1",
                "element_type": "Image",
                "exists_in_input": True,
                "is_new_element": False,
                "t_start": 0.0,
                "t_end": 10.0,
                "x": 60.0,
                "y": 100.0,
                "width": 960.0,
                "height": 900.0,
                "z_index": 1,
                "role": "background",
                "must_not_cover": ["caption_1"],
                "can_be_covered_by": [],
                "sync_reference": None,
                "content_reference": "topic image",
                "behavior": "show",
            },
        ],
        "timeline_summary": [{"segment_id": "s1", "t_start": 0.0, "t_end": 10.0, "what_is_visible": [], "what_is_audible": [], "main_focus": "caption"}],
    }


def test_visual_element_outside_canvas_fails() -> None:
    data = _base_output()
    data["element_property_table"][2]["x"] = 500
    data["element_property_table"][2]["width"] = 700
    result = validate_llm1_output(data, _schema(), _current_state())
    assert not result["valid"]
    assert any("exceeds canvas width" in e for e in result["errors"])


def test_caption_covered_by_higher_z_image_fails() -> None:
    data = _base_output()
    data["element_property_table"][2].update({"x": 50, "y": 1450, "width": 980, "height": 260, "z_index": 5, "role": "foreground"})
    result = validate_llm1_output(data, _schema(), _current_state())
    assert not result["valid"]
    assert any("covered by" in e.lower() for e in result["errors"])


def test_audio_element_with_xy_fails() -> None:
    data = _base_output()
    data["element_property_table"][0]["x"] = 10
    result = validate_llm1_output(data, _schema(), _current_state())
    assert not result["valid"]
    assert any("audio-only element" in e for e in result["errors"])


def test_invalid_behavior_fails() -> None:
    data = _base_output()
    data["edit_decisions"][0]["element_type"] = "Music"
    data["edit_decisions"][0]["action"] = "place"
    result = validate_llm1_output(data, _schema(), _current_state())
    assert not result["valid"]
    assert any("forbidden" in e for e in result["errors"])


def test_valid_plan_passes() -> None:
    data = _base_output()
    # avoid must_not_cover conflict for baseline valid case
    data["element_property_table"][2]["must_not_cover"] = []
    result = validate_llm1_output(data, _schema(), _current_state())
    assert result["valid"]
    assert result["errors"] == []


def test_json_creator_merges_llm1_llm2_outputs() -> None:
    llm1 = _base_output()
    llm2 = {
        "styled_element_table": [
            {
                "element_id": "caption_1",
                "font_family": "Inter",
                "font_size": 60,
                "font_weight": "bold",
                "text_color": "#FFFFFF",
                "highlight_color": "#FFD84D",
                "background_color": "#000000",
                "opacity": 0.95,
                "border_radius": 6,
                "shadow": "soft",
                "animation_in": "fade_in",
                "animation_out": "fade_out",
                "animation_during": None,
                "transition": None,
                "crop": None,
                "scale": None,
                "rotation": None,
                "volume": None,
                "extra_renderer_props": {"stroke_width": 3},
            }
        ]
    }
    original_elements = {
        "elements": [
            {"element_id": "audio_1", "properties": {"source_uri": "assets/inputs/audio.wav"}},
            {"element_id": "caption_1", "properties": {"text": "hello world"}},
            {"element_id": "image_1", "properties": {"source_uri": "assets/inputs/image.jpg"}},
        ]
    }
    out = create_renderer_json(llm1, llm2, original_elements, {"width": 1080, "height": 1920, "fps": 30}, 10.0)
    by_id = {e["id"]: e for e in out["elements"]}
    assert "caption_1" in by_id
    assert by_id["caption_1"]["style"]["font_family"] == "Inter"
    assert by_id["caption_1"]["style"]["stroke_width"] == 3
    assert by_id["audio_1"]["source"] == "assets/inputs/audio.wav"
