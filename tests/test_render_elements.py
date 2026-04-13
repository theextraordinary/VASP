import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running this file directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vasp.core.serialization import serialize_element_json  # noqa: E402
from vasp.render.element_renderer import render_from_json  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


def _render_if_fixture_exists(name: str) -> None:
    path = FIXTURES / name
    if not path.exists():
        return
    actions_json, props_json = serialize_element_json(str(path))
    actions_path = path.with_name("elements.json")
    props_path = path.with_name("elementsProps.json")
    actions_json["properties_path"] = str(props_path)
    with open(actions_path, "w", encoding="utf-8") as handle:
        json.dump(actions_json, handle, indent=2)
    with open(props_path, "w", encoding="utf-8") as handle:
        json.dump(props_json, handle, indent=2)
    render_from_json(str(actions_path), strict=True)


def test_render_caption() -> None:
    _render_if_fixture_exists("caption_input.json")


def test_render_image() -> None:
    _render_if_fixture_exists("image_input.json")


def test_render_gif() -> None:
    _render_if_fixture_exists("gif_input.json")


def test_render_video() -> None:
    _render_if_fixture_exists("video_input.json")


def test_render_figure() -> None:
    _render_if_fixture_exists("figure_input.json")


def test_render_music() -> None:
    _render_if_fixture_exists("music_input.json")


def test_render_sfx() -> None:
    _render_if_fixture_exists("sfx_input.json")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render element fixtures to videos.")
    parser.add_argument(
        "--only",
        choices=[
            "caption",
            "image",
            "image3",
            "combine",
            "reel",
            "story",
            "gif",
            "video",
            "figure",
            "music",
            "sfx",
        ],
        help="Render a single element type fixture.",
    )
    args = parser.parse_args()

    mapping = {
        "caption": "caption_input.json",
        "image": "image_input.json",
        "image3": "image_three_input.json",
        "combine": "combine_input.json",
        "reel": "creative_reel_input.json",
        "story": "video_music_caption_input.json",
        "gif": "gif_input.json",
        "video": "video_input.json",
        "figure": "figure_input.json",
        "music": "music_input.json",
        "sfx": "sfx_input.json",
    }

    if args.only:
        _render_if_fixture_exists(mapping[args.only])
    else:
        for name in mapping.values():
            _render_if_fixture_exists(name)
