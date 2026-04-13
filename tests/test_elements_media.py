import json
from pathlib import Path

from vasp.core.elements import Caption, Figure, GIF, Image, Music, Sfx, Timing, Video


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _skip_if_missing(uri: str) -> bool:
    return not (ROOT / uri).exists()


def test_image_element() -> None:
    data = _load("image_input.json")
    element = data["element"]
    if _skip_if_missing(element["source_uri"]):
        return
    element = Image(
        id=element["id"],
        timing=Timing(**element["timing"]),
        source_uri=element["source_uri"],
        transform=element.get("transform", {}),
    )
    assert element.source_uri.endswith("image.jpg")


def test_gif_element() -> None:
    data = _load("gif_input.json")
    element = data["element"]
    if _skip_if_missing(element["source_uri"]):
        return
    element = GIF(
        id=element["id"],
        timing=Timing(**element["timing"]),
        source_uri=element["source_uri"],
        loop=element.get("loop", True),
        transform=element.get("transform", {}),
    )
    assert element.loop is True


def test_video_element() -> None:
    data = _load("video_input.json")
    element = data["element"]
    if _skip_if_missing(element["source_uri"]):
        return
    element = Video(
        id=element["id"],
        timing=Timing(**element["timing"]),
        source_uri=element["source_uri"],
        trim_in=element.get("trim_in", 0.0),
        trim_out=element.get("trim_out"),
        has_audio=element.get("has_audio", True),
        transform=element.get("transform", {}),
    )
    assert element.has_audio is True


def test_figure_element() -> None:
    data = _load("figure_input.json")
    element = data["element"]
    if _skip_if_missing(element["payload_uri"]):
        return
    element = Figure(
        id=element["id"],
        timing=Timing(**element["timing"]),
        figure_type=element.get("figure_type", "shape"),
        payload_uri=element.get("payload_uri"),
        transform=element.get("transform", {}),
    )
    assert element.figure_type == "sticker"


def test_music_element() -> None:
    data = _load("music_input.json")
    element = data["element"]
    if _skip_if_missing(element["source_uri"]):
        return
    element = Music(
        id=element["id"],
        timing=Timing(**element["timing"]),
        source_uri=element["source_uri"],
        loop=element.get("loop", True),
        volume=element.get("volume", 1.0),
    )
    assert element.volume == 0.8


def test_sfx_element() -> None:
    data = _load("sfx_input.json")
    element = data["element"]
    if _skip_if_missing(element["source_uri"]):
        return
    element = Sfx(
        id=element["id"],
        timing=Timing(**element["timing"]),
        source_uri=element["source_uri"],
        volume=element.get("volume", 1.0),
    )
    assert element.volume == 1.0


def test_caption_element_basic() -> None:
    element = Caption(id="cap_test", timing=Timing(start=0.0, duration=1.0), text="Test")
    assert element.text == "Test"
