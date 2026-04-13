import json
import random
from pathlib import Path

from vasp.core.elements import Caption, Timing


FIXTURES = Path(__file__).parent / "fixtures"


def _load_input() -> dict:
    with open(FIXTURES / "caption_input.json", "r", encoding="utf-8") as handle:
        return json.load(handle)


def _generate_captions(payload: dict) -> list[Caption]:
    width = payload["video"]["size"]["width"]
    height = payload["video"]["size"]["height"]
    element = payload["element"]
    words = element["text"].split()
    colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4"]
    rng = random.Random(42)

    captions: list[Caption] = []
    for idx, word in enumerate(words):
        start = float(element["timing"]["start"])
        duration = float(element["timing"]["duration"])
        x = rng.uniform(0, width)
        y = rng.uniform(0, height)
        captions.append(
            Caption(
                id=f"{element['id']}_word_{idx}",
                timing=Timing(start=start, duration=duration),
                text=word,
                language=element.get("language"),
                metadata={"word_index": idx, "color": colors[idx % len(colors)]},
                transform={"x": x, "y": y},
            )
        )
    return captions


def test_caption_generation_matches_expected() -> None:
    payload = _load_input()
    captions = _generate_captions(payload)
    output = {"captions": [caption.model_dump() for caption in captions]}

    with open(FIXTURES / "caption_output.json", "r", encoding="utf-8") as handle:
        expected = json.load(handle)

    assert output == expected
