from __future__ import annotations

from typing import Any

from vasp.pipeline.edit_pipeline import run_edit_pipeline


class _FakeClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses

    def generate_json(self, req):  # type: ignore[no-untyped-def]
        return self._responses.pop(0)


def test_pipeline_integration_without_render(tmp_path) -> None:
    media_paths = ["input/clip.mp4"]
    output_path = str(tmp_path / "final.mp4")

    llm1 = {
        "decisions": [
            {
                "element_id": "video_1",
                "t_start": 0.0,
                "t_end": 2.0,
                "purpose": "intro",
                "placement_zone": "center",
            }
        ]
    }
    inter = {
        "version": "1.0",
        "video": {"size": {"width": 1080, "height": 1920}, "fps": 30, "bg_color": [0, 0, 0]},
        "elements": [
            {
                "element_id": "video_1",
                "timing": {"start": 0.0, "duration": 2.0},
                "actions": [{"t_start": 0.0, "t_end": 2.0, "op": "show", "params": {}}],
            }
        ],
    }

    client = _FakeClient([llm1, inter])
    inter_path = run_edit_pipeline(
        instruction="simple edit",
        media_paths=media_paths,
        output_path=output_path,
        llm_client=client,  # type: ignore[arg-type]
        extra_options={
            "instruction_1": "focus on pacing",
            "instruction_2": "highlight keywords",
            "instruction_3": "clean captions",
        },
        render=False,
    )
    assert inter_path.name == "inter.json"
    assert (tmp_path / "a2v_prompt.txt").exists()
