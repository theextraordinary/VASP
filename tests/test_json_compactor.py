from __future__ import annotations

import json

from vasp.core.json_compactor import compact_json_outputs


def test_compactor_removes_null_fields(tmp_path) -> None:
    elements = {
        "elements": [
            {"element_id": "e1", "type": "caption", "about": None, "aim": "highlight", "timing": {"start": 0.0, "duration": 1.0}}
        ],
        "media_context": {"analysis": {"m1": {"transcript": None}}},
    }
    props = {
        "elements": [
            {
                "element_id": "e1",
                "properties": {"type": "caption", "language": None, "text": "Hello"},
            }
        ]
    }

    elements_txt, props_txt = compact_json_outputs(
        elements_json=elements,
        element_props_json=props,
        output_dir=tmp_path,
    )
    elements_payload = json.loads(elements_txt.read_text(encoding="utf-8"))
    props_payload = json.loads(props_txt.read_text(encoding="utf-8"))

    assert "about" not in elements_payload["elements"][0]
    assert "transcript" not in elements_payload["media_context"]["analysis"]["m1"]
    assert "language" not in props_payload["elements"][0]["properties"]
    assert props_payload["elements"][0]["properties"]["text"] == "Hello"

