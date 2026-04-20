from __future__ import annotations

from copy import deepcopy
from typing import Any


BACKGROUND_PRESETS: dict[str, dict[str, Any]] = {
    "cinematic_letterbox_grain": {
        "type": "vignette",
        "color": "#050505",
        "secondary_color": "#1A1A1A",
        "grain": 0.12,
        "vignette": 0.55,
        "notes": "dark film look like professional emotional edits",
    },
    "muted_film_gold": {
        "type": "gradient",
        "color": "#030303",
        "secondary_color": "#7C5C12",
        "grain": 0.10,
        "vignette": 0.45,
    },
    "soft_documentary_gray": {
        "type": "vignette",
        "color": "#0A0A0A",
        "secondary_color": "#3F3F46",
        "grain": 0.08,
        "vignette": 0.5,
    },
    "neon_science_blue": {
        "type": "gradient",
        "color": "#06111F",
        "secondary_color": "#0369A1",
        "grain": 0.04,
        "vignette": 0.35,
    },
    "breaking_news_red": {
        "type": "gradient",
        "color": "#111827",
        "secondary_color": "#991B1B",
        "grain": 0.06,
        "vignette": 0.4,
    },
    "comedy_pop_pink": {
        "type": "gradient",
        "color": "#1F102A",
        "secondary_color": "#DB2777",
        "grain": 0.03,
        "vignette": 0.25,
    },
}

CAPTION_PRESETS: dict[str, dict[str, Any]] = {
    "cinematic_big_center": {
        "font_family": "Montserrat",
        "font_size": 82,
        "font_weight": "900",
        "text_color": "#F8F5DC",
        "highlight_color": "#FACC15",
        "background_color": "rgba(0,0,0,0.0)",
        "align": "center",
        "animation": {"type": "slide_up", "intensity": "high"},
    },
    "documentary_bottom_clean": {
        "font_family": "Inter",
        "font_size": 64,
        "font_weight": "800",
        "text_color": "#FFFFFF",
        "highlight_color": "#FBBF24",
        "background_color": "rgba(0,0,0,0.45)",
        "align": "center",
        "animation": {"type": "word_reveal", "intensity": "medium"},
    },
    "bold_news_pop": {
        "font_family": "Bebas Neue",
        "font_size": 78,
        "font_weight": "900",
        "text_color": "#FFFFFF",
        "highlight_color": "#F43F5E",
        "background_color": "rgba(0,0,0,0.35)",
        "align": "center",
        "animation": {"type": "pop", "intensity": "medium"},
    },
    "soft_emotional_script": {
        "font_family": "Poppins",
        "font_size": 70,
        "font_weight": "800",
        "text_color": "#FFF7ED",
        "highlight_color": "#FDBA74",
        "background_color": "rgba(0,0,0,0.0)",
        "align": "center",
        "animation": {"type": "fade", "intensity": "medium"},
    },
}

VISUAL_PRESETS: dict[str, dict[str, Any]] = {
    "center_cinematic_media": {
        "x": 0,
        "y": 544,
        "width": 1080,
        "height": 800,
        "z_index": 3,
        "opacity": 1.0,
        "fit": "contain",
    },
    "center_image_card": {
        "x": 140,
        "y": 520,
        "width": 800,
        "height": 820,
        "z_index": 3,
        "opacity": 1.0,
        "fit": "contain",
        "round_corners": 28,
        "shadow": True,
    },
    "full_bleed_safe": {
        "x": 0,
        "y": 260,
        "width": 1080,
        "height": 980,
        "z_index": 3,
        "opacity": 1.0,
        "fit": "cover",
    },
}

ANIMATION_PRESETS: dict[str, dict[str, str]] = {
    "caption_slide_up": {"type": "slide_up", "intensity": "high"},
    "caption_word_reveal": {"type": "word_reveal", "intensity": "medium"},
    "caption_pop": {"type": "pop", "intensity": "medium"},
    "visual_subtle_zoom": {"type": "subtle_zoom", "intensity": "low"},
    "visual_float": {"type": "float", "intensity": "low"},
    "visual_none": {"type": "none", "intensity": "low"},
}

DESIGN_COMBOS: list[dict[str, str]] = [
    {
        "name": "cinematic_letterbox_grain",
        "background": "cinematic_letterbox_grain",
        "caption": "cinematic_big_center",
        "visual": "center_cinematic_media",
        "visual_animation": "visual_subtle_zoom",
    },
    {
        "name": "muted_film_gold",
        "background": "muted_film_gold",
        "caption": "documentary_bottom_clean",
        "visual": "center_image_card",
        "visual_animation": "visual_float",
    },
    {
        "name": "soft_documentary_gray",
        "background": "soft_documentary_gray",
        "caption": "documentary_bottom_clean",
        "visual": "center_cinematic_media",
        "visual_animation": "visual_none",
    },
    {
        "name": "neon_science_blue",
        "background": "neon_science_blue",
        "caption": "cinematic_big_center",
        "visual": "center_cinematic_media",
        "visual_animation": "visual_subtle_zoom",
    },
    {
        "name": "breaking_news_red",
        "background": "breaking_news_red",
        "caption": "bold_news_pop",
        "visual": "full_bleed_safe",
        "visual_animation": "visual_none",
    },
    {
        "name": "comedy_pop_pink",
        "background": "comedy_pop_pink",
        "caption": "bold_news_pop",
        "visual": "center_image_card",
        "visual_animation": "visual_float",
    },
]

FIXED_VISUAL_LAYOUT = {
    "x": 0,
    "y": 544,
    "width": 1080,
    "height": 800,
    "z_index": 3,
    "opacity": 1.0,
    "fit": "contain",
}
BOTTOM_CAPTION_LAYOUT = {"x": 90, "y": 1450, "width": 900, "height": 300, "z_index": 10}
CENTER_CAPTION_LAYOUT = {"x": 120, "y": 760, "width": 840, "height": 420, "z_index": 10}


def _segment_seed(segment: dict[str, Any]) -> int:
    sid = str(segment.get("segment_id") or "")
    digits = "".join(ch for ch in sid if ch.isdigit())
    if digits:
        return int(digits)
    return int(float(segment.get("t_start", 0.0) or 0.0) * 10)


def _media_type(segment: dict[str, Any]) -> str:
    media = segment.get("media") if isinstance(segment.get("media"), dict) else {}
    return str(media.get("type") or segment.get("type") or "").lower()


def choose_refiner_design_preset(
    segment: dict[str, Any],
    creativity_level: int,
    has_visual: bool,
    previous_preset: str | None = None,
) -> dict[str, Any]:
    if creativity_level <= 0:
        combo = {
            "name": "deterministic_default",
            "background": {"type": "solid", "color": "#000000", "secondary_color": "#111827", "opacity": 1.0},
            "caption": {
                "font_family": "Inter",
                "font_size": 64,
                "font_weight": "800",
                "text_color": "#FFFFFF",
                "highlight_color": "#FFD84D",
                "background_color": "rgba(0,0,0,0.45)",
                "align": "center",
                "animation": {"type": "word_reveal", "intensity": "medium"},
            },
            "visual_layout": deepcopy(FIXED_VISUAL_LAYOUT),
            "caption_layout": deepcopy(BOTTOM_CAPTION_LAYOUT if has_visual else CENTER_CAPTION_LAYOUT),
            "visual_animation": deepcopy(ANIMATION_PRESETS["visual_none"]),
        }
        return combo

    candidates = DESIGN_COMBOS
    media_type = _media_type(segment)
    if not has_visual:
        preferred = ["cinematic_letterbox_grain", "soft_documentary_gray", "muted_film_gold", "neon_science_blue"]
    elif media_type == "image":
        preferred = ["muted_film_gold", "comedy_pop_pink", "soft_documentary_gray", "cinematic_letterbox_grain"]
    elif media_type in {"video", "gif", "sticker"}:
        preferred = ["cinematic_letterbox_grain", "neon_science_blue", "breaking_news_red", "soft_documentary_gray"]
    else:
        preferred = [c["name"] for c in candidates]

    ordered = [c for name in preferred for c in candidates if c["name"] == name]
    ordered.extend(c for c in candidates if c not in ordered)
    seed = _segment_seed(segment)
    choice = ordered[seed % len(ordered)]
    if creativity_level >= 4 and previous_preset and choice["name"] == previous_preset and len(ordered) > 1:
        choice = ordered[(seed + 1) % len(ordered)]

    caption = deepcopy(CAPTION_PRESETS[choice["caption"]])
    caption_layout = deepcopy(BOTTOM_CAPTION_LAYOUT if has_visual else CENTER_CAPTION_LAYOUT)
    if not has_visual:
        caption["font_size"] = max(int(caption.get("font_size", 70)), 76)
    visual_layout = deepcopy(VISUAL_PRESETS[choice["visual"]])
    if media_type in {"video", "gif", "sticker"}:
        visual_layout = deepcopy(VISUAL_PRESETS["center_cinematic_media"])
    elif media_type == "image" and creativity_level >= 2 and choice["visual"] == "full_bleed_safe":
        visual_layout = deepcopy(VISUAL_PRESETS["center_image_card"])

    background = deepcopy(BACKGROUND_PRESETS[choice["background"]])
    background["opacity"] = 1.0
    return {
        "name": choice["name"],
        "background": background,
        "caption": caption,
        "caption_layout": caption_layout,
        "visual_layout": visual_layout,
        "visual_animation": deepcopy(ANIMATION_PRESETS[choice["visual_animation"]]),
    }
