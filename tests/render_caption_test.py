from __future__ import annotations

from vasp.core.serialization import serialize_element_json
from vasp.render.element_renderer import render_from_json


def main() -> None:
    actions_json, props_json = serialize_element_json("tests/fixtures/caption_input.json")
    actions_path = "tests/fixtures/elements.json"
    props_path = "tests/fixtures/elementsProps.json"
    actions_json["properties_path"] = props_path
    with open(actions_path, "w", encoding="utf-8") as handle:
        import json

        json.dump(actions_json, handle, indent=2)
    with open(props_path, "w", encoding="utf-8") as handle:
        import json

        json.dump(props_json, handle, indent=2)
    render_from_json(actions_path, strict=True)


if __name__ == "__main__":
    main()
