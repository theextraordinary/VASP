from __future__ import annotations

from copy import deepcopy
from typing import Any


BACKGROUND_PRESETS: dict[str, dict[str, Any]] = {
    "black_reel_canvas": {
        "type": "solid",
        "color": "#000000",
        "secondary_color": "#050505",
        "opacity": 1.0,
        "grain": 0.015,
        "vignette": 0.18,
        "blur_strength": 0.0,
        "glow": 0.0,
        "notes": "premium minimal black cinematic reel background"
    },

    "dark_film_vignette": {
        "type": "vignette",
        "color": "#040404",
        "secondary_color": "#18181B",
        "opacity": 1.0,
        "grain": 0.035,
        "vignette": 0.78,
        "blur_strength": 0.12,
        "glow": 0.04,
        "notes": "high-end Netflix style dark cinematic backdrop"
    },

    "warm_memory_gold": {
        "type": "gradient",
        "color": "#120A05",
        "secondary_color": "#B45309",
        "opacity": 1.0,
        "grain": 0.025,
        "vignette": 0.42,
        "blur_strength": 0.08,
        "glow": 0.14,
        "notes": "warm nostalgic cinematic memory tone with rich amber glow"
    },

    "cold_blue_night": {
        "type": "gradient",
        "color": "#020617",
        "secondary_color": "#2563EB",
        "opacity": 1.0,
        "grain": 0.02,
        "vignette": 0.38,
        "blur_strength": 0.06,
        "glow": 0.08,
        "notes": "premium cold blue documentary night atmosphere"
    },

    "nostalgic_gray_blur": {
        "type": "blur",
        "color": "#090909",
        "secondary_color": "#71717A",
        "opacity": 1.0,
        "grain": 0.03,
        "vignette": 0.45,
        "blur_strength": 0.22,
        "glow": 0.03,
        "notes": "luxury soft gray blur inspired by modern documentaries"
    },

    "cinematic_letterbox_grain": {
        "type": "vignette",
        "color": "#030303",
        "secondary_color": "#111111",
        "opacity": 1.0,
        "grain": 0.065,
        "vignette": 0.82,
        "blur_strength": 0.05,
        "glow": 0.02,
        "notes": "professional cinematic theater-grade film grain look"
    },

    "muted_film_gold": {
        "type": "gradient",
        "color": "#0B0907",
        "secondary_color": "#A16207",
        "opacity": 1.0,
        "grain": 0.045,
        "vignette": 0.52,
        "blur_strength": 0.08,
        "glow": 0.10,
        "notes": "premium muted gold cinematic educational backdrop"
    },

    "neon_science_blue": {
        "type": "gradient",
        "color": "#020B18",
        "secondary_color": "#0EA5E9",
        "opacity": 1.0,
        "grain": 0.015,
        "vignette": 0.28,
        "blur_strength": 0.04,
        "glow": 0.18,
        "notes": "modern neon science-tech cinematic glow"
    },

    "breaking_news_red": {
        "type": "gradient",
        "color": "#111827",
        "secondary_color": "#DC2626",
        "opacity": 1.0,
        "grain": 0.03,
        "vignette": 0.48,
        "blur_strength": 0.05,
        "glow": 0.09,
        "notes": "high-energy broadcast news urgency backdrop"
    },

    "comedy_pop_pink": {
        "type": "gradient",
        "color": "#170B20",
        "secondary_color": "#EC4899",
        "opacity": 1.0,
        "grain": 0.012,
        "vignette": 0.22,
        "blur_strength": 0.03,
        "glow": 0.16,
        "notes": "modern creator-style playful comedy aesthetic"
    },

    "soft_documentary_gray": {
        "type": "vignette",
        "color": "#09090B",
        "secondary_color": "#52525B",
        "opacity": 1.0,
        "grain": 0.028,
        "vignette": 0.58,
        "blur_strength": 0.09,
        "glow": 0.02,
        "notes": "premium restrained documentary neutral background"
    },

    "mystery_violet": {
        "type": "vignette",
        "color": "#090611",
        "secondary_color": "#7C3AED",
        "opacity": 1.0,
        "grain": 0.04,
        "vignette": 0.82,
        "blur_strength": 0.10,
        "glow": 0.22,
        "notes": "deep cinematic violet mystery atmosphere with bloom"
    },
}

CAPTION_PRESETS: dict[str, dict[str, Any]] = {
    "small_cinematic_quote": {"font_family": "Montserrat", "font_size": 42, "font_weight": "600", "text_color": "#FFFFFF", "highlight_color": "#FBBF24", "background_color": "rgba(0,0,0,0.0)", "stroke_color": "#000000", "stroke_width": 2, "align": "center"},
    "large_reel_keyword": {"font_family": "Montserrat", "font_size": 86, "font_weight": "900", "text_color": "#FFFFFF", "highlight_color": "#FACC15", "background_color": "rgba(0,0,0,0.0)", "stroke_color": "#000000", "stroke_width": 5, "align": "center"},
    "talking_head_clean": {"font_family": "Poppins", "font_size": 56, "font_weight": "800", "text_color": "#FFFFFF", "highlight_color": "#FDE047", "background_color": "rgba(0,0,0,0.0)", "stroke_color": "#000000", "stroke_width": 4, "align": "left"},
    "bottom_subtitle_clean": {"font_family": "Inter", "font_size": 52, "font_weight": "700", "text_color": "#FFFFFF", "highlight_color": "#FBBF24", "background_color": "rgba(0,0,0,0.35)", "stroke_color": "#000000", "stroke_width": 3, "align": "center"},
    "yellow_word_emphasis": {"font_family": "Montserrat", "font_size": 64, "font_weight": "900", "text_color": "#FFFFFF", "highlight_color": "#FACC15", "background_color": "rgba(0,0,0,0.0)", "stroke_color": "#000000", "stroke_width": 4, "align": "center"},
    "cinematic_big_center": {"font_family": "Montserrat", "font_size": 82, "font_weight": "900", "text_color": "#F8F5DC", "highlight_color": "#FACC15", "background_color": "rgba(0,0,0,0.0)", "stroke_color": "#000000", "stroke_width": 4, "align": "center"},
    "documentary_bottom_clean": {"font_family": "Inter", "font_size": 64, "font_weight": "800", "text_color": "#FFFFFF", "highlight_color": "#FBBF24", "background_color": "rgba(0,0,0,0.45)", "stroke_color": "#000000", "stroke_width": 3, "align": "center"},
    "bold_news_pop": {"font_family": "Bebas Neue", "font_size": 78, "font_weight": "900", "text_color": "#FFFFFF", "highlight_color": "#F43F5E", "background_color": "rgba(0,0,0,0.35)", "stroke_color": "#000000", "stroke_width": 4, "align": "center"},
    "soft_emotional_script": {"font_family": "Poppins", "font_size": 70, "font_weight": "800", "text_color": "#FFF7ED", "highlight_color": "#FDBA74", "background_color": "rgba(0,0,0,0.0)", "stroke_color": "#000000", "stroke_width": 3, "align": "center"},
    "meme_bold_pop": {"font_family": "Montserrat", "font_size": 88, "font_weight": "900", "text_color": "#FFFFFF", "highlight_color": "#FACC15", "background_color": "rgba(0,0,0,0.0)", "stroke_color": "#000000", "stroke_width": 5, "align": "center"},
    "science_clean_blue": {"font_family": "Poppins", "font_size": 62, "font_weight": "800", "text_color": "#E0F2FE", "highlight_color": "#38BDF8", "background_color": "rgba(2,6,23,0.35)", "stroke_color": "#000000", "stroke_width": 3, "align": "center"},
}

LAYOUT_PRESETS: dict[str, dict[str, Any]] = {
    "caption_only_center": {"x": 120, "y": 760, "width": 840, "height": 360, "z_index": 10},
    "caption_only_lower_center": {"x": 120, "y": 1050, "width": 840, "height": 300, "z_index": 10},
    "caption_bottom_safe": {"x": 90, "y": 1450, "width": 900, "height": 300, "z_index": 10},
    "caption_mid_overlay": {"x": 100, "y": 980, "width": 880, "height": 260, "z_index": 10},
    "visual_center_800h": {"x": 0, "y": 544, "width": 1080, "height": 800, "z_index": 3, "opacity": 1.0, "fit": "contain"},
    "visual_landscape_middle": {"x": 0, "y": 500, "width": 1080, "height": 610, "z_index": 3, "opacity": 1.0, "fit": "contain"},
    "visual_portrait_full": {"x": 0, "y": 0, "width": 1080, "height": 1920, "z_index": 3, "opacity": 1.0, "fit": "cover"},
    "image_card_center": {"x": 160, "y": 480, "width": 760, "height": 860, "z_index": 3, "opacity": 1.0, "fit": "contain", "round_corners": 28, "shadow": True},
    "visual_safe_top_feature": {"x": 80, "y": 260, "width": 920, "height": 860, "z_index": 3, "opacity": 1.0, "fit": "contain"},
    "visual_square_center_card": {"x": 140, "y": 470, "width": 800, "height": 800, "z_index": 3, "opacity": 1.0, "fit": "contain", "round_corners": 24, "shadow": True},
}

ANIMATION_PRESETS: dict[str, dict[str, Any]] = {
    # Caption animations
    "caption_fade_soft": {
        "type": "fade",
        "intensity": "medium",
        "duration": 0.18,
        "easing": "ease_out",
        "notes": "clean soft caption fade for documentary narration",
    },
    "caption_slide_up_clean": {
        "type": "slide_up",
        "intensity": "medium",
        "duration": 0.24,
        "distance": 34,
        "easing": "ease_out_cubic",
        "notes": "professional reel-style upward caption entrance",
    },
    "caption_pop_keyword": {
        "type": "pop",
        "intensity": "high",
        "duration": 0.14,
        "scale_from": 0.88,
        "scale_to": 1.0,
        "easing": "back_out",
        "notes": "strong keyword pop for punchy moments",
    },
    "caption_word_reveal_fast": {
        "type": "word_reveal",
        "intensity": "medium",
        "duration": 0.0,
        "per_word_delay": 0.035,
        "easing": "linear",
        "notes": "fast synced word reveal for short-form captions",
    },
    "caption_typewriter": {
        "type": "typewriter",
        "intensity": "medium",
        "duration": 0.0,
        "char_delay": 0.012,
        "cursor": False,
        "notes": "controlled typewriter for mystery/history beats",
    },
    "caption_kinetic_bounce": {
        "type": "bounce",
        "intensity": "medium",
        "duration": 0.18,
        "scale_from": 0.92,
        "scale_to": 1.0,
        "easing": "elastic_out",
        "notes": "energetic caption bounce for comedy or surprise",
    },
    "caption_blur_snap": {
        "type": "blur_in",
        "intensity": "medium",
        "duration": 0.2,
        "blur_from": 10,
        "blur_to": 0,
        "easing": "ease_out",
        "notes": "premium blur-to-sharp title reveal",
    },
    "caption_glow_pulse": {
        "type": "glow_pulse",
        "intensity": "medium",
        "duration": 0.35,
        "glow_strength": 0.35,
        "notes": "subtle glow emphasis for science/space words",
    },
    "caption_stomp": {
        "type": "stomp",
        "intensity": "high",
        "duration": 0.12,
        "scale_from": 1.18,
        "scale_to": 1.0,
        "easing": "back_out",
        "notes": "impactful text hit for strong facts or punchlines",
    },
    "caption_wave_reveal": {
        "type": "wave_reveal",
        "intensity": "medium",
        "duration": 0.28,
        "wave_amplitude": 10,
        "per_word_delay": 0.025,
        "notes": "stylish sequential reveal without feeling chaotic",
    },

    # Visual animations
    "visual_slow_zoom_in": {
        "type": "subtle_zoom",
        "intensity": "low",
        "scale_from": 1.0,
        "scale_to": 1.06,
        "easing": "ease_in_out",
        "notes": "classic Ken Burns slow zoom-in",
    },
    "visual_slow_zoom_out": {
        "type": "subtle_zoom_out",
        "intensity": "low",
        "scale_from": 1.06,
        "scale_to": 1.0,
        "easing": "ease_in_out",
        "notes": "gentle zoom-out for reveal or conclusion",
    },
    "visual_float_soft": {
        "type": "float",
        "intensity": "low",
        "amplitude": 12,
        "period": 2.8,
        "notes": "soft floating movement for images/cards",
    },
    "visual_punch_zoom": {
        "type": "pulse",
        "intensity": "medium",
        "scale_from": 1.0,
        "scale_to": 1.08,
        "duration": 0.22,
        "easing": "back_out",
        "notes": "quick punch zoom for emphasis",
    },
    "visual_pulse": {
        "type": "pulse",
        "intensity": "medium",
        "scale_from": 1.0,
        "scale_to": 1.05,
        "period": 1.2,
        "notes": "subtle repeating visual pulse",
    },
    "visual_drift_left": {
        "type": "drift",
        "intensity": "low",
        "x_from": 18,
        "x_to": -18,
        "easing": "ease_in_out",
        "notes": "cinematic horizontal drift",
    },
    "visual_drift_right": {
        "type": "drift",
        "intensity": "low",
        "x_from": -18,
        "x_to": 18,
        "easing": "ease_in_out",
        "notes": "cinematic horizontal drift opposite direction",
    },
    "visual_card_lift": {
        "type": "card_lift",
        "intensity": "medium",
        "y_from": 26,
        "y_to": 0,
        "scale_from": 0.96,
        "scale_to": 1.0,
        "easing": "ease_out_cubic",
        "notes": "premium image card entrance",
    },
    "visual_tilt_float": {
        "type": "tilt_float",
        "intensity": "low",
        "rotation_from": -1.5,
        "rotation_to": 1.5,
        "amplitude": 8,
        "notes": "gentle social-media card motion",
    },
    "visual_shake_hit": {
        "type": "shake",
        "intensity": "medium",
        "duration": 0.18,
        "amplitude": 8,
        "notes": "brief shake for impact only",
    },
    "visual_none": {
        "type": "none",
        "intensity": "low",
        "notes": "no animation; clean stable composition",
    },
}


TRANSITION_PRESETS: dict[str, dict[str, Any]] = {
    "quick_cut": {
        "type": "cut",
        "duration": 0.0,
        "notes": "instant professional cut",
    },
    "cut": {
        "type": "cut",
        "duration": 0.0,
        "notes": "alias for quick_cut",
    },
    "soft_fade": {
        "type": "fade",
        "duration": 0.18,
        "easing": "ease_out",
        "notes": "clean short fade",
    },
    "cinematic_fade": {
        "type": "fade",
        "duration": 0.35,
        "easing": "ease_in_out",
        "notes": "slower cinematic fade",
    },
    "pop_in": {
        "type": "pop",
        "duration": 0.12,
        "scale_from": 0.88,
        "scale_to": 1.0,
        "easing": "back_out",
        "notes": "snappy pop transition",
    },
    "slide_up_in": {
        "type": "slide",
        "direction": "up",
        "duration": 0.22,
        "distance": 80,
        "easing": "ease_out_cubic",
        "notes": "modern slide-up entrance",
    },
    "slide_down_in": {
        "type": "slide",
        "direction": "down",
        "duration": 0.22,
        "distance": 80,
        "easing": "ease_out_cubic",
        "notes": "clean slide-down entrance",
    },
    "slide_left_in": {
        "type": "slide",
        "direction": "left",
        "duration": 0.22,
        "distance": 90,
        "easing": "ease_out_cubic",
        "notes": "horizontal slide transition",
    },
    "slide_right_in": {
        "type": "slide",
        "direction": "right",
        "duration": 0.22,
        "distance": 90,
        "easing": "ease_out_cubic",
        "notes": "horizontal slide transition",
    },
    "zoom_in_cut": {
        "type": "zoom",
        "duration": 0.18,
        "scale_from": 0.96,
        "scale_to": 1.0,
        "easing": "ease_out",
        "notes": "small zoom-in cut for emphasis",
    },
    "zoom_blur_in": {
        "type": "zoom_blur",
        "duration": 0.24,
        "scale_from": 1.08,
        "scale_to": 1.0,
        "blur_from": 12,
        "blur_to": 0,
        "easing": "ease_out_cubic",
        "notes": "premium energetic zoom blur reveal",
    },
    "blur_fade": {
        "type": "blur_fade",
        "duration": 0.25,
        "blur_from": 14,
        "blur_to": 0,
        "easing": "ease_out",
        "notes": "soft professional blur fade",
    },
    "whip_left": {
        "type": "whip",
        "direction": "left",
        "duration": 0.16,
        "motion_blur": 18,
        "notes": "fast creator-style whip transition",
    },
    "whip_right": {
        "type": "whip",
        "direction": "right",
        "duration": 0.16,
        "motion_blur": 18,
        "notes": "fast creator-style whip transition",
    },
    "flash_cut": {
        "type": "flash",
        "duration": 0.10,
        "color": "#FFFFFF",
        "opacity": 0.55,
        "notes": "quick flash for dramatic beat",
    },
    "dip_to_black": {
        "type": "dip",
        "duration": 0.28,
        "color": "#000000",
        "notes": "clean cinematic dip to black",
    },
}

PRESET_BUNDLES: dict[str, dict[str, str]] = {
    # Premium documentary / history
    "cinematic_history": {
        "background_preset": "warm_memory_gold",
        "caption_preset": "small_cinematic_quote",
        "caption_layout_preset": "caption_only_center",
        "visual_layout_preset": "image_card_center",
        "caption_animation_preset": "caption_blur_snap",
        "visual_animation_preset": "visual_slow_zoom_in",
        "transition_preset": "cinematic_fade",
    },
    "historical_archive_gold": {
        "background_preset": "muted_film_gold",
        "caption_preset": "small_cinematic_quote",
        "caption_layout_preset": "caption_only_lower_center",
        "visual_layout_preset": "image_card_center",
        "caption_animation_preset": "caption_fade_soft",
        "visual_animation_preset": "visual_float_soft",
        "transition_preset": "dip_to_black",
    },

    # Science / space
    "science_discovery": {
        "background_preset": "neon_science_blue",
        "caption_preset": "science_clean_blue",
        "caption_layout_preset": "caption_bottom_safe",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_word_reveal_fast",
        "visual_animation_preset": "visual_slow_zoom_in",
        "transition_preset": "soft_fade",
    },
    "space_neon": {
        "background_preset": "cold_blue_night",
        "caption_preset": "science_clean_blue",
        "caption_layout_preset": "caption_bottom_safe",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_glow_pulse",
        "visual_animation_preset": "visual_slow_zoom_in",
        "transition_preset": "zoom_blur_in",
    },
    "cosmic_reveal": {
        "background_preset": "mystery_violet",
        "caption_preset": "large_reel_keyword",
        "caption_layout_preset": "caption_mid_overlay",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_stomp",
        "visual_animation_preset": "visual_punch_zoom",
        "transition_preset": "zoom_blur_in",
    },

    # War / news / documentary
    "war_documentary": {
        "background_preset": "soft_documentary_gray",
        "caption_preset": "documentary_bottom_clean",
        "caption_layout_preset": "caption_bottom_safe",
        "visual_layout_preset": "visual_landscape_middle",
        "caption_animation_preset": "caption_fade_soft",
        "visual_animation_preset": "visual_slow_zoom_in",
        "transition_preset": "cinematic_fade",
    },
    "breaking_news": {
        "background_preset": "breaking_news_red",
        "caption_preset": "bold_news_pop",
        "caption_layout_preset": "caption_bottom_safe",
        "visual_layout_preset": "visual_landscape_middle",
        "caption_animation_preset": "caption_pop_keyword",
        "visual_animation_preset": "visual_none",
        "transition_preset": "quick_cut",
    },
    "urgent_war_report": {
        "background_preset": "breaking_news_red",
        "caption_preset": "bold_news_pop",
        "caption_layout_preset": "caption_mid_overlay",
        "visual_layout_preset": "visual_landscape_middle",
        "caption_animation_preset": "caption_stomp",
        "visual_animation_preset": "visual_shake_hit",
        "transition_preset": "flash_cut",
    },

    # Comedy / meme / reaction
    "comedy_reaction": {
        "background_preset": "comedy_pop_pink",
        "caption_preset": "meme_bold_pop",
        "caption_layout_preset": "caption_mid_overlay",
        "visual_layout_preset": "visual_square_center_card",
        "caption_animation_preset": "caption_kinetic_bounce",
        "visual_animation_preset": "visual_punch_zoom",
        "transition_preset": "pop_in",
    },
    "meme_pop": {
        "background_preset": "comedy_pop_pink",
        "caption_preset": "large_reel_keyword",
        "caption_layout_preset": "caption_mid_overlay",
        "visual_layout_preset": "visual_square_center_card",
        "caption_animation_preset": "caption_pop_keyword",
        "visual_animation_preset": "visual_punch_zoom",
        "transition_preset": "pop_in",
    },
    "chaotic_funny_reaction": {
        "background_preset": "comedy_pop_pink",
        "caption_preset": "meme_bold_pop",
        "caption_layout_preset": "caption_only_center",
        "visual_layout_preset": "visual_square_center_card",
        "caption_animation_preset": "caption_wave_reveal",
        "visual_animation_preset": "visual_tilt_float",
        "transition_preset": "whip_right",
    },

    # Emotional / motivational
    "emotional_quote": {
        "background_preset": "cinematic_letterbox_grain",
        "caption_preset": "soft_emotional_script",
        "caption_layout_preset": "caption_only_center",
        "visual_layout_preset": "image_card_center",
        "caption_animation_preset": "caption_slide_up_clean",
        "visual_animation_preset": "visual_float_soft",
        "transition_preset": "soft_fade",
    },
    "motivational_dark": {
        "background_preset": "dark_film_vignette",
        "caption_preset": "large_reel_keyword",
        "caption_layout_preset": "caption_only_center",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_stomp",
        "visual_animation_preset": "visual_slow_zoom_in",
        "transition_preset": "cinematic_fade",
    },
    "dreamy_memory": {
        "background_preset": "nostalgic_gray_blur",
        "caption_preset": "soft_emotional_script",
        "caption_layout_preset": "caption_only_lower_center",
        "visual_layout_preset": "image_card_center",
        "caption_animation_preset": "caption_blur_snap",
        "visual_animation_preset": "visual_float_soft",
        "transition_preset": "blur_fade",
    },

    # Clean creator / education
    "clean_educational": {
        "background_preset": "black_reel_canvas",
        "caption_preset": "talking_head_clean",
        "caption_layout_preset": "caption_bottom_safe",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_word_reveal_fast",
        "visual_animation_preset": "visual_slow_zoom_in",
        "transition_preset": "soft_fade",
    },
    "premium_explainer": {
        "background_preset": "dark_film_vignette",
        "caption_preset": "bottom_subtitle_clean",
        "caption_layout_preset": "caption_bottom_safe",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_slide_up_clean",
        "visual_animation_preset": "visual_slow_zoom_in",
        "transition_preset": "soft_fade",
    },
    "minimal_creator": {
        "background_preset": "black_reel_canvas",
        "caption_preset": "yellow_word_emphasis",
        "caption_layout_preset": "caption_mid_overlay",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_pop_keyword",
        "visual_animation_preset": "visual_none",
        "transition_preset": "quick_cut",
    },

    # Mystery / suspense
    "dark_mystery": {
        "background_preset": "dark_film_vignette",
        "caption_preset": "small_cinematic_quote",
        "caption_layout_preset": "caption_only_lower_center",
        "visual_layout_preset": "image_card_center",
        "caption_animation_preset": "caption_typewriter",
        "visual_animation_preset": "visual_float_soft",
        "transition_preset": "cinematic_fade",
    },
    "violet_mystery_reveal": {
        "background_preset": "mystery_violet",
        "caption_preset": "small_cinematic_quote",
        "caption_layout_preset": "caption_only_center",
        "visual_layout_preset": "image_card_center",
        "caption_animation_preset": "caption_typewriter",
        "visual_animation_preset": "visual_tilt_float",
        "transition_preset": "blur_fade",
    },

    # Fast social-media pacing
    "fast_reel_hook": {
        "background_preset": "black_reel_canvas",
        "caption_preset": "large_reel_keyword",
        "caption_layout_preset": "caption_only_center",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_stomp",
        "visual_animation_preset": "visual_punch_zoom",
        "transition_preset": "flash_cut",
    },
    "retention_boost": {
        "background_preset": "neon_science_blue",
        "caption_preset": "large_reel_keyword",
        "caption_layout_preset": "caption_mid_overlay",
        "visual_layout_preset": "visual_center_800h",
        "caption_animation_preset": "caption_kinetic_bounce",
        "visual_animation_preset": "visual_pulse",
        "transition_preset": "zoom_in_cut",
    },
}


def _get(table: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    return deepcopy(table.get(name, {}))


def get_background_preset(name: str) -> dict[str, Any]:
    return _get(BACKGROUND_PRESETS, name)


def get_caption_preset(name: str) -> dict[str, Any]:
    return _get(CAPTION_PRESETS, name)


def get_layout_preset(name: str) -> dict[str, Any]:
    return _get(LAYOUT_PRESETS, name)


def get_animation_preset(name: str) -> dict[str, Any]:
    return _get(ANIMATION_PRESETS, name)


def get_transition_preset(name: str) -> dict[str, Any]:
    return _get(TRANSITION_PRESETS, name)


def list_refiner_presets() -> dict[str, list[str]]:
    return {
        "background_presets": sorted(BACKGROUND_PRESETS),
        "caption_presets": sorted(CAPTION_PRESETS),
        "layout_presets": sorted(LAYOUT_PRESETS),
        "animation_presets": sorted(ANIMATION_PRESETS),
        "transition_presets": sorted(TRANSITION_PRESETS),
        "preset_bundles": sorted(PRESET_BUNDLES),
    }


def resolve_refiner_preset_bundle(bundle: dict[str, Any] | str | None) -> dict[str, Any]:
    names: dict[str, Any] = {}
    if isinstance(bundle, str):
        names.update(PRESET_BUNDLES.get(bundle, {}))
        names["preset_bundle"] = bundle
    elif isinstance(bundle, dict):
        if isinstance(bundle.get("preset_bundle"), str):
            names.update(PRESET_BUNDLES.get(str(bundle["preset_bundle"]), {}))
        names.update({k: v for k, v in bundle.items() if isinstance(v, str)})
    return {
        "preset_bundle": names.get("preset_bundle"),
        "background": get_background_preset(str(names.get("background_preset") or "")),
        "caption_style": get_caption_preset(str(names.get("caption_preset") or "")),
        "caption_layout": get_layout_preset(str(names.get("caption_layout_preset") or "")),
        "visual_layout": get_layout_preset(str(names.get("visual_layout_preset") or "")),
        "caption_animation": get_animation_preset(str(names.get("caption_animation_preset") or "")),
        "visual_animation": get_animation_preset(str(names.get("visual_animation_preset") or "")),
        "transition": get_transition_preset(str(names.get("transition_preset") or "")),
        "names": names,
    }
