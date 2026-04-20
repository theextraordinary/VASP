from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from vasp.pipeline.structured_edit_pipeline import run_structured_edit_pipeline


def dummy_llm1_client(_prompt: str) -> str:
    return json.dumps(
        {
            "edit_decisions": [
                {
                    "decision_id": "d1",
                    "element_id": "image_1",
                    "element_type": "Image",
                    "action": "show",
                    "t_start": 0.0,
                    "t_end": 6.0,
                    "purpose": "Visual context",
                    "reason": "Topic match",
                    "depends_on": [],
                    "avoid_overlap_with": ["caption_track_1"],
                    "placement_zone": "center",
                    "notes_for_styler": "soft fade",
                }
            ],
            "element_property_table": [
                {
                    "element_id": "audio_1",
                    "element_type": "Music",
                    "exists_in_input": True,
                    "is_new_element": False,
                    "t_start": 0.0,
                    "t_end": 6.0,
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
                    "element_id": "image_1",
                    "element_type": "Image",
                    "exists_in_input": True,
                    "is_new_element": False,
                    "t_start": 0.0,
                    "t_end": 6.0,
                    "x": 60.0,
                    "y": 160.0,
                    "width": 960.0,
                    "height": 960.0,
                    "z_index": 1,
                    "role": "background",
                    "must_not_cover": ["caption_track_1"],
                    "can_be_covered_by": [],
                    "sync_reference": None,
                    "content_reference": "topic image",
                    "behavior": "show",
                },
                {
                    "element_id": "caption_track_1",
                    "element_type": "Caption",
                    "exists_in_input": True,
                    "is_new_element": False,
                    "t_start": 0.2,
                    "t_end": 5.8,
                    "x": 80.0,
                    "y": 1500.0,
                    "width": 920.0,
                    "height": 220.0,
                    "z_index": 3,
                    "role": "caption",
                    "must_not_cover": [],
                    "can_be_covered_by": [],
                    "sync_reference": "audio_1",
                    "content_reference": "sample caption text",
                    "behavior": "show",
                },
            ],
            "timeline_summary": [
                {
                    "segment_id": "s1",
                    "t_start": 0.0,
                    "t_end": 6.0,
                    "what_is_visible": ["image_1", "caption_track_1"],
                    "what_is_audible": ["audio_1"],
                    "main_focus": "caption + image context",
                }
            ],
        }
    )


def dummy_llm2_client(_prompt: str) -> str:
    return json.dumps(
        {
            "styled_element_table": [
                {
                    "element_id": "caption_track_1",
                    "font_family": "Montserrat",
                    "font_size": 58,
                    "font_weight": "bold",
                    "text_color": "#FFFFFF",
                    "highlight_color": "#FFD84D",
                    "background_color": "#000000",
                    "opacity": 0.95,
                    "border_radius": 8,
                    "shadow": "soft",
                    "animation_in": "fade_in",
                    "animation_out": "fade_out",
                    "animation_during": None,
                    "transition": None,
                    "crop": None,
                    "scale": None,
                    "rotation": None,
                    "volume": None,
                    "extra_renderer_props": {},
                }
            ]
        }
    )


def main() -> None:
    elements = json.loads(Path("examples/sample_elements.json").read_text(encoding="utf-8"))
    instruction = Path("examples/sample_user_instruction.txt").read_text(encoding="utf-8").strip()
    result = run_structured_edit_pipeline(
        user_instruction=instruction,
        elements=elements,
        canvas={"width": 1080, "height": 1920, "fps": 30},
        duration=6.0,
        llm1_client=dummy_llm1_client,
        llm2_client=dummy_llm2_client,
    )
    out = Path("output/structured_pipeline_renderer_json_example.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
