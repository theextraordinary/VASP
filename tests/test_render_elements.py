import json
from pathlib import Path

from vasp.core.serialization import serialize_element_json
from vasp.render.element_renderer import render_from_json


FIXTURES = Path(__file__).parent / "fixtures"


def _render_if_fixture_exists(name: str) -> None:
    path = FIXTURES / name
    if not path.exists():
        return
    element_json = serialize_element_json(str(path))
    out_path = path.with_name(path.stem + "_element.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(element_json, handle, indent=2)
    render_from_json(str(out_path), strict=True)


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
