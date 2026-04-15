from __future__ import annotations

from typing import Any


# These presets are grounded to what renderer supports today.
BACKGROUND_PRESETS: dict[str, dict[str, Any]] = {
    "clean_black": {"background_style": "clean_black", "notes": "Plain dark canvas"},
    "grain_vignette": {"background_style": "grain_vignette", "notes": "Film grain + vignette"},
    "calendar_dark": {"background_style": "calendar_dark", "notes": "Grid/calendar treatment"},
    "roman_columns": {"background_style": "roman_columns", "notes": "Stylized column boxes"},
    "cinematic_red": {"background_style": "cinematic_red", "notes": "Assassination danger tint, no grid"},
    "night_blue": {"background_style": "night_blue", "notes": "Dark blue cinematic tint, light vignette"},
    "morning_energy": {"background_style": "morning_energy", "notes": "Warm sunrise energy palette"},
    "mint_daylight": {"background_style": "mint_daylight", "notes": "Fresh daylight mint palette"},
    "sky_breeze": {"background_style": "sky_breeze", "notes": "Light blue morning palette"},
    "neutral_dark": {"background_style": "neutral_dark", "notes": "Minimal dark style without pattern"},
    "clean_white": {"background_style": "clean_white", "notes": "White minimal background"},
    "white_pattern": {"background_style": "white_pattern", "notes": "White patterned background"},
}

FRAME_PRESETS: dict[str, dict[str, Any]] = {
    "none": {"round_corners": 0},
    "rounded_soft": {"round_corners": 18},
    "rounded_card": {"round_corners": 24},
}

SHAPE_PRESETS: dict[str, dict[str, Any]] = {
    "center_card": {"x": 540.0, "y": 960.0, "scale": 1.0},
    "upper_feature": {"x": 540.0, "y": 820.0, "scale": 1.25},
    "lower_caption_safe": {"x": 540.0, "y": 1570.0, "scale": 1.0},
}

CAPTION_DESIGN_REFS: list[str] = [
    "clean_caption",
    "meme_caption",
]

VISUAL_DESIGN_REFS: list[str] = [
    "rounded_card",
]

EVENT_PRESETS: dict[str, dict[str, Any]] = {
    "none": {"notes": "No overlay pattern; pure background style only"},
    "soft_frame": {"type": "frame", "opacity": 0.08, "thickness": 10},
    "top_panel": {"type": "panel", "x": "0", "y": "0", "w": "iw", "h": "220", "opacity": 0.16},
    "bottom_panel": {"type": "panel", "x": "0", "y": "ih-300", "w": "iw", "h": "300", "opacity": 0.16},
    "stripe_h": {"type": "stripe_h", "opacity": 0.12, "band_h": 120, "gap_h": 260},
    "stripe_v": {"type": "stripe_v", "opacity": 0.12, "band_w": 120, "gap_w": 320},
    "grid_light": {"type": "grid", "opacity": 0.08, "cell_w": 160, "cell_h": 160, "thickness": 1},
}


def render_design_catalog_text() -> str:
    lines: list[str] = []
    lines.append("BACKGROUND_PRESETS:")
    for key, value in BACKGROUND_PRESETS.items():
        lines.append(f"- {key}: {value}")
    lines.append("FRAME_PRESETS:")
    for key, value in FRAME_PRESETS.items():
        lines.append(f"- {key}: {value}")
    lines.append("SHAPE_PRESETS:")
    for key, value in SHAPE_PRESETS.items():
        lines.append(f"- {key}: {value}")
    lines.append(f"CAPTION_DESIGN_REFS: {CAPTION_DESIGN_REFS}")
    lines.append(f"VISUAL_DESIGN_REFS: {VISUAL_DESIGN_REFS}")
    lines.append("EVENT_PRESETS:")
    for key, value in EVENT_PRESETS.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)
