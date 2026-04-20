from __future__ import annotations

from copy import deepcopy
from typing import Any


CREATIVITY_LEVELS = (0, 1, 2, 3, 4, 5)

FIXED_VISUAL_LAYOUT = {
    "x": 0,
    "y": 544,
    "width": 1080,
    "height": 800,
    "z_index": 3,
    "opacity": 1.0,
    "fit": "contain",
    "caption_safe": True,
}
BOTTOM_CAPTION_LAYOUT = {"x": 90, "y": 1450, "width": 900, "height": 300, "z_index": 10}
CENTER_CAPTION_LAYOUT = {"x": 120, "y": 820, "width": 840, "height": 300, "z_index": 10}
DEFAULT_CAPTION_STYLE = {
    "font_family": "Inter",
    "font_size": 64,
    "font_weight": "800",
    "text_color": "#FFFFFF",
    "highlight_color": "#FFD84D",
    "stroke_color": "#000000",
    "stroke_width": 3,
    "background_color": "rgba(0,0,0,0.45)",
    "align": "center",
}

SAFE_FONTS = ["Inter", "Arial", "Montserrat", "Poppins", "Bebas Neue"]
SAFE_COLORS = ["#FFFFFF", "#FFD84D", "#000000", "#111827", "#F97316", "#38BDF8", "#22C55E", "#F43F5E", "#A78BFA", "#14B8A6"]
ALL_ANIMATIONS = [
    "none",
    "word_reveal",
    "fade",
    "pop",
    "typewriter",
    "slide_up",
    "bounce",
    "blur_in",
    "glow_pulse",
    "stomp",
    "wave_reveal",
    "subtle_zoom",
    "subtle_zoom_out",
    "pulse",
    "float",
    "drift",
    "card_lift",
    "tilt_float",
    "shake",
]
SAFE_ANIMATIONS = [
    "none",
    "word_reveal",
    "fade",
    "pop",
    "typewriter",
    "slide_up",
    "bounce",
    "glow_pulse",
    "subtle_zoom",
    "subtle_zoom_out",
    "pulse",
    "float",
    "drift",
]
ALL_TRANSITIONS = ["none", "cut", "fade", "slide", "zoom", "pop", "zoom_blur", "blur_fade", "whip", "flash", "dip"]
LEVEL1_ANIMATIONS = ["none", "word_reveal", "fade", "pop", "typewriter", "slide_up"]
LEVEL1_TRANSITIONS = ["cut", "fade", "slide", "zoom", "pop"]
CREATIVE_CAPTION_STYLES = [
    {"font_family": "Inter", "font_size": 68, "text_color": "#FFFFFF", "highlight_color": "#FFD84D", "background_color": "rgba(0,0,0,0.48)"},
    {"font_family": "Montserrat", "font_size": 64, "text_color": "#F8FAFC", "highlight_color": "#38BDF8", "background_color": "transparent", "background_opacity": 0.0},
    {"font_family": "Poppins", "font_size": 66, "text_color": "#FFF7ED", "highlight_color": "#F97316", "background_color": "rgba(30,41,59,0.36)"},
    {"font_family": "Bebas Neue", "font_size": 74, "text_color": "#FFFFFF", "highlight_color": "#22C55E", "background_color": "transparent", "background_opacity": 0.0},
    {"font_family": "Arial", "font_size": 62, "text_color": "#E0F2FE", "highlight_color": "#FACC15", "background_color": "rgba(8,47,73,0.50)"},
]
CREATIVE_DESIGN_PRESETS = [
    {
        "name": "cinematic_midnight_gold",
        "background": {"type": "gradient", "color": "#020617", "secondary_color": "#78350F", "opacity": 0.92},
        "caption_style": {"font_family": "Inter", "text_color": "#FFFFFF", "highlight_color": "#FBBF24", "background_color": "rgba(15,23,42,0.34)"},
        "caption_animation": {"type": "slide_up", "intensity": "medium"},
    },
    {
        "name": "neon_science_blue",
        "background": {"type": "gradient", "color": "#08111F", "secondary_color": "#0369A1", "opacity": 0.9},
        "caption_style": {"font_family": "Montserrat", "text_color": "#E0F2FE", "highlight_color": "#38BDF8", "background_color": "transparent", "background_opacity": 0.0},
        "caption_animation": {"type": "word_reveal", "intensity": "medium"},
    },
    {
        "name": "warm_documentary_orange",
        "background": {"type": "vignette", "color": "#1C1917", "secondary_color": "#C2410C", "opacity": 0.86},
        "caption_style": {"font_family": "Poppins", "text_color": "#FFF7ED", "highlight_color": "#FB923C", "background_color": "rgba(28,25,23,0.38)"},
        "caption_animation": {"type": "fade", "intensity": "medium"},
    },
    {
        "name": "breaking_news_red",
        "background": {"type": "gradient", "color": "#111827", "secondary_color": "#991B1B", "opacity": 0.88},
        "caption_style": {"font_family": "Bebas Neue", "text_color": "#FFFFFF", "highlight_color": "#F43F5E", "background_color": "transparent", "background_opacity": 0.0},
        "caption_animation": {"type": "pop", "intensity": "high"},
    },
    {
        "name": "nature_emerald",
        "background": {"type": "gradient", "color": "#052E16", "secondary_color": "#0F766E", "opacity": 0.86},
        "caption_style": {"font_family": "Arial", "text_color": "#ECFDF5", "highlight_color": "#34D399", "background_color": "rgba(6,78,59,0.34)"},
        "caption_animation": {"type": "slide_up", "intensity": "medium"},
    },
    {
        "name": "mystery_violet",
        "background": {"type": "vignette", "color": "#0F1024", "secondary_color": "#6D28D9", "opacity": 0.9},
        "caption_style": {"font_family": "Montserrat", "text_color": "#F5F3FF", "highlight_color": "#A78BFA", "background_color": "rgba(15,16,36,0.42)"},
        "caption_animation": {"type": "typewriter", "intensity": "medium"},
    },
    {
        "name": "comedy_pop_pink",
        "background": {"type": "pattern", "color": "#1F102A", "secondary_color": "#DB2777", "opacity": 0.84},
        "caption_style": {"font_family": "Poppins", "text_color": "#FFFFFF", "highlight_color": "#F9A8D4", "background_color": "transparent", "background_opacity": 0.0},
        "caption_animation": {"type": "pop", "intensity": "high"},
    },
    {
        "name": "clean_creator_slate",
        "background": {"type": "solid", "color": "#0F172A", "secondary_color": "#334155", "opacity": 1.0},
        "caption_style": {"font_family": "Inter", "text_color": "#F8FAFC", "highlight_color": "#22C55E", "background_color": "rgba(15,23,42,0.45)"},
        "caption_animation": {"type": "word_reveal", "intensity": "medium"},
    },
]
CREATIVE_BACKGROUNDS = [
    dict(preset["background"]) for preset in CREATIVE_DESIGN_PRESETS
]
CREATIVE_CAPTION_ANIMATIONS = ["word_reveal", "slide_up", "pop", "fade", "typewriter", "bounce", "glow_pulse", "stomp", "wave_reveal"]


def _preset_rules_text() -> str:
    lines = ["Available high-creativity design presets. Pick one per segment when level is 3-5:"]
    for preset in CREATIVE_DESIGN_PRESETS:
        bg = preset["background"]
        st = preset["caption_style"]
        anim = preset["caption_animation"]
        lines.append(
            "- {name}: background {bg_type} {color}->{secondary}, caption {font} text {text} highlight {highlight}, animation {anim_type}.".format(
                name=preset["name"],
                bg_type=bg["type"],
                color=bg["color"],
                secondary=bg["secondary_color"],
                font=st["font_family"],
                text=st["text_color"],
                highlight=st["highlight_color"],
                anim_type=anim["type"],
            )
        )
    return "\n".join(lines)


def _rules(level: int) -> str:
    common = [
        f"Creativity level is {level}/5. Follow the creativity policy exactly. Do not exceed the freedom allowed by this level.",
        "Always keep captions readable, visible, and inside the 1080x1920 canvas.",
        "Never make visual opacity below 1.0 unless explicitly allowed by the policy.",
        "Return valid JSON only.",
    ]
    if level >= 3:
        common.append(_preset_rules_text())
    by_level = {
        0: [
            "LEVEL 0 - deterministic/consistent.",
            "Use the exact same visual layout for every visual: x=0,y=544,width=1080,height=800,z_index=3,opacity=1.0,fit=contain,caption_safe=true.",
            "Use only fixed caption layouts: with visual x=90,y=1450,width=900,height=300; no visual x=120,y=820,width=840,height=300.",
            "Use one caption style for the whole video: Inter, white text, #FFD84D highlight, rgba(0,0,0,0.45) background.",
            "Use word_reveal medium captions, none/low visual animation, cut/fade transitions, and black/dark backgrounds.",
            "No per-segment or per-cue style changes.",
        ],
        1: [
            "LEVEL 1 - transition/animation creativity only.",
            "Visual layout, caption layout, caption font, caption size, caption colors, and background stay fixed like level 0.",
            "Only animation and transition may vary from safe presets: cut, fade, slide, zoom, pop; word_reveal, fade, pop, typewriter, slide_up.",
        ],
        2: [
            "LEVEL 2 - default mild creativity.",
            "Visual layout and caption layout stay fixed exactly like level 0.",
            "Caption font, size, and colors stay consistent like level 0 to preserve readability and timing confidence.",
            "Use only simple caption motion: word_reveal or fade. Do not use typewriter, bounce, glow, stomp, wave, or chaotic animation.",
            "Visual media must not animate; use the source playback only for GIF/video motion.",
            "Background should lightly vary by segment using dark/subtle colors.",
            "No visual placement changes and no chaotic per-word styling.",
        ],
        3: [
            "LEVEL 3 - medium creativity.",
            "Visual layout stays fixed exactly like level 0.",
            "Caption layout may vary only slightly when visual is active: bottom y between 1380 and 1500.",
            "If no visual is active, keep captions in the center reading zone around y=760 to y=900.",
            "Caption font/color/background and background timeline should change by segment. Keep size consistent within each segment.",
            "Choose a named design preset for the segment and reflect that choice in background_timeline.reason.",
        ],
        4: [
            "LEVEL 4 - high creativity.",
            "Visual layout stays fixed exactly like level 0.",
            "Caption layout, font, colors, background, animation, and transition can change by segment or cue.",
            "If no visual is active, captions must still stay in the center reading zone, not at the bottom.",
            "Captions must remain visible, readable, inside screen, and uncluttered.",
            "Use varied named design presets across adjacent segments; do not repeat the same background unless it is intentional continuity.",
        ],
        5: [
            "LEVEL 5 - maximum creativity.",
            "Visual layout may vary creatively, but must stay inside 1080x1920 and preserve caption readability.",
            "Captions may use different fonts, colors, sizes, layouts per segment or cue.",
            "If no visual is active, captions must be centered visually in the canvas.",
            "Background timeline, animations, and transitions may use all available presets.",
            "Strongly vary design presets across segments while keeping the video intentional and readable.",
            "Still enforce one visual at a time, no broken JSON, no invisible elements, and an intentional final look.",
        ],
    }
    return "\n".join(common + by_level[level])


def get_creativity_policy(level: int) -> dict[str, Any]:
    if level not in CREATIVITY_LEVELS:
        raise ValueError(f"creativity must be one of {CREATIVITY_LEVELS}, got {level}")
    fixed_layout = level <= 4
    fixed_caption_layout = level <= 1
    fixed_caption_style = level <= 2
    return {
        "level": level,
        "visual_layout_mode": "fixed" if fixed_layout else "creative_clamped",
        "caption_layout_mode": "fixed" if fixed_caption_layout else "safe_variable",
        "caption_style_mode": "fixed" if fixed_caption_style else "readable_variable",
        "animation_mode": "fixed" if level <= 2 else "safe_variable" if level < 5 else "creative_clamped",
        "transition_mode": "simple" if level == 0 else "safe_variable" if level < 5 else "creative_clamped",
        "background_mode": "fixed_dark" if level <= 1 else "subtle_variable" if level <= 3 else "creative_clamped",
        "allowed_visual_layouts": [deepcopy(FIXED_VISUAL_LAYOUT)] if fixed_layout else ["inside_canvas_caption_safe"],
        "allowed_caption_layouts": [deepcopy(BOTTOM_CAPTION_LAYOUT), deepcopy(CENTER_CAPTION_LAYOUT)],
        "allowed_fonts": ["Inter"] if fixed_caption_style else SAFE_FONTS,
        "allowed_colors": ["#FFFFFF", "#FFD84D", "rgba(0,0,0,0.45)"] if fixed_caption_style else SAFE_COLORS,
        "allowed_animations": ["word_reveal", "none"] if level == 0 else LEVEL1_ANIMATIONS if level == 1 else ["none", "word_reveal", "fade"] if level == 2 else ALL_ANIMATIONS,
        "allowed_transitions": ["cut", "fade"] if level == 0 else LEVEL1_TRANSITIONS if level == 1 else ALL_TRANSITIONS,
        "allowed_design_presets": deepcopy(CREATIVE_DESIGN_PRESETS) if level >= 3 else [],
        "rules_text": _rules(level),
    }


def _f(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def clamp_visual_layout(layout: dict[str, Any] | None, level: int, warnings: list[str] | None = None) -> dict[str, Any]:
    if level <= 4:
        if warnings is not None and layout and any(layout.get(k) != FIXED_VISUAL_LAYOUT[k] for k in ("x", "y", "width", "height")):
            warnings.append(f"creativity_{level}_visual_layout_normalized")
        return deepcopy(FIXED_VISUAL_LAYOUT)
    src = layout if isinstance(layout, dict) else {}
    w = _clamp(_f(src.get("width"), FIXED_VISUAL_LAYOUT["width"]), 120.0, 1080.0)
    h = _clamp(_f(src.get("height"), FIXED_VISUAL_LAYOUT["height"]), 120.0, 1920.0)
    x = _clamp(_f(src.get("x"), FIXED_VISUAL_LAYOUT["x"]), 0.0, 1080.0 - w)
    y = _clamp(_f(src.get("y"), FIXED_VISUAL_LAYOUT["y"]), 0.0, 1920.0 - h)
    return {
        "x": round(x, 3),
        "y": round(y, 3),
        "width": round(w, 3),
        "height": round(h, 3),
        "z_index": int(_f(src.get("z_index"), 3)),
        "opacity": _clamp(_f(src.get("opacity"), 1.0), 0.15, 1.0),
        "fit": str(src.get("fit") or "contain"),
        "caption_safe": bool(src.get("caption_safe", True)),
    }


def normalize_caption_layout(
    layout: dict[str, Any] | None,
    level: int,
    visual_active: bool,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    fixed = BOTTOM_CAPTION_LAYOUT if visual_active else CENTER_CAPTION_LAYOUT
    if level <= 1:
        if warnings is not None and layout and any(layout.get(k) != fixed[k] for k in ("x", "y", "width", "height")):
            warnings.append(f"creativity_{level}_caption_layout_normalized")
        return deepcopy(fixed)
    src = layout if isinstance(layout, dict) else {}
    w = _clamp(_f(src.get("width"), fixed["width"]), 420.0, 1040.0)
    h = _clamp(_f(src.get("height"), fixed["height"]), 120.0, 420.0)
    x = _clamp(_f(src.get("x"), fixed["x"]), 0.0, 1080.0 - w)
    if not visual_active:
        # Even at high creativity, caption-only moments should feel centered.
        y_lo, y_hi = (740.0, 920.0) if level >= 3 else (800.0, 860.0)
        y = _clamp(_f(src.get("y"), fixed["y"]), y_lo, y_hi)
    elif level == 2:
        y = _clamp(_f(src.get("y"), fixed["y"]), 1430.0, 1490.0)
    elif level == 3:
        y_lo, y_hi = 1380.0, 1500.0
        y = _clamp(_f(src.get("y"), fixed["y"]), y_lo, y_hi)
    else:
        y = _clamp(_f(src.get("y"), fixed["y"]), 1120.0, 1540.0)
    return {"x": round(x, 3), "y": round(y, 3), "width": round(w, 3), "height": round(h, 3), "z_index": int(_f(src.get("z_index"), 10))}


def normalize_caption_style(style: dict[str, Any] | None, level: int, warnings: list[str] | None = None) -> dict[str, Any]:
    if level <= 2:
        if warnings is not None and style:
            warnings.append(f"creativity_{level}_caption_style_normalized")
        return deepcopy(DEFAULT_CAPTION_STYLE)
    src = dict(DEFAULT_CAPTION_STYLE)
    if isinstance(style, dict):
        src.update({k: v for k, v in style.items() if v is not None})
    src["font_family"] = str(src.get("font_family") or "Inter")
    src["font_size"] = int(_clamp(_f(src.get("font_size"), 64), 56.0 if level <= 4 else 40.0, 76.0 if level <= 4 else 96.0))
    src["text_color"] = str(src.get("text_color") or src.get("color") or "#FFFFFF")
    src["highlight_color"] = str(src.get("highlight_color") or "#FFD84D")
    src["background_color"] = str(src.get("background_color") or "rgba(0,0,0,0.45)")
    if "background_opacity" in src:
        src["background_opacity"] = _clamp(_f(src.get("background_opacity"), 0.45), 0.0, 1.0)
    return src


def creative_caption_style(seed: int, level: int, base: dict[str, Any] | None = None) -> dict[str, Any]:
    if level >= 3:
        style = dict(CREATIVE_DESIGN_PRESETS[seed % len(CREATIVE_DESIGN_PRESETS)]["caption_style"])
    else:
        style = dict(CREATIVE_CAPTION_STYLES[seed % len(CREATIVE_CAPTION_STYLES)])
    if isinstance(base, dict):
        # Keep explicit refiner choices where present, but fill missing fields with
        # an intentionally varied design so conservative outputs still improve.
        if level >= 3:
            # At high creativity, repeated conservative refiner styles are the
            # common failure mode. Preserve structural/readability details, but
            # let the preset drive typography, color, box/no-box, and emphasis.
            for key in ("font_weight", "stroke_color", "stroke_width", "align", "vertical_align"):
                if base.get(key) is not None:
                    style[key] = base[key]
        else:
            style.update({k: v for k, v in base.items() if v is not None})
    if level >= 4:
        style["font_size"] = [58, 64, 70, 76, 82][seed % 5]
    elif level == 3:
        style["font_size"] = [58, 62, 66, 70, 74][seed % 5]
    else:
        style["font_size"] = [58, 62, 66, 70][seed % 4]
    style.setdefault("font_weight", "800")
    style.setdefault("stroke_color", "#000000")
    style.setdefault("stroke_width", 3)
    style.setdefault("align", "center")
    return normalize_caption_style(style, level)


def creative_caption_animation(seed: int, level: int, base: dict[str, Any] | None = None) -> dict[str, Any]:
    if level <= 1:
        return allowed_animation(base or {"type": "word_reveal", "intensity": "medium"}, level)
    if level >= 3:
        preset_anim = dict(CREATIVE_DESIGN_PRESETS[seed % len(CREATIVE_DESIGN_PRESETS)]["caption_animation"])
        if level >= 4 and seed % 2:
            preset_anim["intensity"] = "high"
        return allowed_animation(preset_anim, level)
    typ = CREATIVE_CAPTION_ANIMATIONS[seed % len(CREATIVE_CAPTION_ANIMATIONS)]
    return allowed_animation({"type": typ, "intensity": "medium"}, level)


def creative_background(seed: int, level: int, t_start: float, t_end: float, reason: str = "creative_caption_design") -> dict[str, Any]:
    preset = CREATIVE_DESIGN_PRESETS[seed % len(CREATIVE_DESIGN_PRESETS)]
    bg = dict(preset["background"])
    if level <= 1:
        bg = {"type": "solid", "color": "#000000", "secondary_color": "#111827", "opacity": 1.0}
    elif level == 2:
        bg["opacity"] = min(float(bg.get("opacity", 0.9)), 0.9)
    bg.update({"t_start": t_start, "t_end": t_end, "reason": f"{reason}:{preset['name']}"})
    return bg


def allowed_animation(animation: dict[str, Any] | None, level: int) -> dict[str, Any]:
    allowed = get_creativity_policy(level)["allowed_animations"]
    src = animation if isinstance(animation, dict) else {}
    typ = str(src.get("type") or ("word_reveal" if level <= 4 else "none"))
    if typ not in allowed:
        typ = "word_reveal" if "word_reveal" in allowed else allowed[0]
    out = {k: v for k, v in src.items() if v is not None}
    out["type"] = typ
    out["intensity"] = str(src.get("intensity") or "medium")
    return out


def allowed_transition(transition: dict[str, Any] | None, level: int) -> dict[str, Any]:
    allowed = get_creativity_policy(level)["allowed_transitions"]
    src = transition if isinstance(transition, dict) else {}
    typ = str(src.get("type") or "fade")
    if typ not in allowed:
        typ = "fade" if "fade" in allowed else allowed[0]
    out = {k: v for k, v in src.items() if v is not None}
    out["type"] = typ
    out["duration"] = _clamp(_f(src.get("duration"), 0.15), 0.0, 0.6)
    return out
