from __future__ import annotations

from vasp.core.serialization import serialize_element_json
from vasp.render.element_renderer import render_from_json


def main() -> None:
    element_json = serialize_element_json("tests/fixtures/caption_input.json")
    out_path = "tests/fixtures/caption_input_element.json"
    with open(out_path, "w", encoding="utf-8") as handle:
        import json

        json.dump(element_json, handle, indent=2)
    render_from_json(out_path, strict=True)


if __name__ == "__main__":
    main()
