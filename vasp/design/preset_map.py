from __future__ import annotations

from typing import Any


def caption_design_params(design_ref: str | None, *, dramatic: bool = False) -> dict[str, Any]:
    """Map a design ref to renderer-supported caption params."""
    name = (design_ref or "").strip().lower()
    if name in {"clean_caption", "clean"}:
        return {"font_size": 58 if dramatic else 50, "font_weight": "bold", "font_style": "normal", "color": "#FFFFFF"}
    if name in {"meme", "meme_caption"}:
        return {"font_size": 62, "font_weight": "bold", "font_style": "normal", "color": "#FFD447"}
    if dramatic:
        return {"font_size": 60, "font_weight": "bold", "font_style": "italic", "color": "#F8F8F8"}
    return {"font_size": 50, "font_weight": "regular", "font_style": "normal", "color": "#FFFFFF"}


def visual_design_params(design_ref: str | None, *, dramatic: bool = False) -> dict[str, Any]:
    """Map a visual design ref to renderer-supported media params."""
    name = (design_ref or "").strip().lower()
    if name in {"card", "rounded_card"}:
        return {"round_corners": 24}
    if dramatic:
        return {"round_corners": 12}
    return {}
