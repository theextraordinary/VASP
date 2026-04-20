from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


PRESET_BACKGROUND_DIR = Path("assets/preset_bgs")

PRESET_BACKGROUND_IMAGES: dict[str, dict[str, Any]] = {
    "bg1": {
        "name": "bg1",
        "path": str(PRESET_BACKGROUND_DIR / "bg1.webp"),
        "about": "white colored grid",
        "best_use": "light and informative parts",
        "tone": "light_informative",
    },
    "bg2": {
        "name": "bg2",
        "path": str(PRESET_BACKGROUND_DIR / "bg2.webp"),
        "about": "dark colored grid",
        "best_use": "dark and informative parts",
        "tone": "dark_informative",
    },
    "bg3": {
        "name": "bg3",
        "path": str(PRESET_BACKGROUND_DIR / "bg3.webp"),
        "about": "dark colored fancy background with open center space",
        "best_use": "segments with visuals placed at center",
        "tone": "dark_visual_center",
    },
    "bg4": {
        "name": "bg4",
        "path": str(PRESET_BACKGROUND_DIR / "bg4.webp"),
        "about": "dark blue cool background",
        "best_use": "caption-only or center-caption segments",
        "tone": "cool_center_caption",
    },
    "bg5": {
        "name": "bg5",
        "path": str(PRESET_BACKGROUND_DIR / "bg5.webp"),
        "about": "white colored paper",
        "best_use": "light and informative parts",
        "tone": "light_paper_informative",
    },
}


def get_preset_background(name: str | None) -> dict[str, Any]:
    return deepcopy(PRESET_BACKGROUND_IMAGES.get(str(name or "").strip(), {}))


def list_preset_backgrounds() -> list[dict[str, Any]]:
    return [deepcopy(v) for _, v in sorted(PRESET_BACKGROUND_IMAGES.items())]


def choose_preset_background(
    *,
    has_visual: bool,
    caption_centered: bool,
    segment_text: str = "",
    creativity_level: int = 2,
    seed: int = 0,
) -> dict[str, Any]:
    text = segment_text.lower()
    if has_visual:
        return get_preset_background("bg3")
    if caption_centered:
        return get_preset_background("bg4")
    if any(word in text for word in ("science", "fact", "explain", "learn", "data", "system", "careful")):
        return get_preset_background("bg2" if creativity_level >= 3 and seed % 2 else "bg1")
    if any(word in text for word in ("memory", "yesterday", "story", "paper", "history")):
        return get_preset_background("bg5")
    return get_preset_background(["bg1", "bg2", "bg4", "bg5"][seed % 4])


def preset_background_prompt_text() -> str:
    lines = [
        "PRESET BACKGROUND IMAGES:",
        "Choose one of these when use_preset_backgrounds=true. Use exact names only.",
    ]
    for item in list_preset_backgrounds():
        lines.append(f"- {item['name']}: {item['about']}; best use: {item['best_use']}; path: {item['path']}")
    return "\n".join(lines)
