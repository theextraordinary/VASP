from __future__ import annotations

from vasp.animation.primitives import AnimationPreset, AnimationType


_PRESETS: dict[str, AnimationPreset] = {
    "subtle_zoom": AnimationPreset(
        id="subtle_zoom",
        type=AnimationType.ZOOM_IN,
        description="Slow, cinematic zoom-in effect.",
        default_params={"from_scale": 1.0, "to_scale": 1.08},
    ),
    "zoom_out_soft": AnimationPreset(
        id="zoom_out_soft",
        type=AnimationType.ZOOM_OUT,
        description="Soft zoom-out reveal.",
        default_params={"from_scale": 1.08, "to_scale": 1.0},
    ),
    "pop": AnimationPreset(
        id="pop",
        type=AnimationType.POP,
        description="Quick scale pop for emphasis.",
        default_params={"peak_scale": 1.15},
    ),
    "pulse": AnimationPreset(
        id="pulse",
        type=AnimationType.PULSE,
        description="Rhythmic size pulse.",
        default_params={"min_scale": 0.98, "max_scale": 1.06},
    ),
    "breathe": AnimationPreset(
        id="breathe",
        type=AnimationType.BREATHE,
        description="Very subtle in-out breathing scale.",
        default_params={"min_scale": 0.995, "max_scale": 1.03},
    ),
    "bounce": AnimationPreset(
        id="bounce",
        type=AnimationType.BOUNCE,
        description="Vertical bounce.",
        default_params={"amplitude_px": 36},
    ),
    "shake": AnimationPreset(
        id="shake",
        type=AnimationType.SHAKE,
        description="Horizontal shake.",
        default_params={"amplitude_px": 14},
    ),
    "wiggle": AnimationPreset(
        id="wiggle",
        type=AnimationType.WIGGLE,
        description="Small rotation wiggle.",
        default_params={"angle_deg": 6},
    ),
    "spin": AnimationPreset(
        id="spin",
        type=AnimationType.SPIN,
        description="Continuous rotation.",
        default_params={"turns": 1},
    ),
    "slide_up": AnimationPreset(
        id="slide_up",
        type=AnimationType.SLIDE_UP,
        description="Slide upward into frame.",
        default_params={"distance_px": 140},
    ),
    "slide_down": AnimationPreset(
        id="slide_down",
        type=AnimationType.SLIDE_DOWN,
        description="Slide downward into frame.",
        default_params={"distance_px": 140},
    ),
    "slide_left": AnimationPreset(
        id="slide_left",
        type=AnimationType.SLIDE_LEFT,
        description="Slide left into frame.",
        default_params={"distance_px": 180},
    ),
    "slide_right": AnimationPreset(
        id="slide_right",
        type=AnimationType.SLIDE_RIGHT,
        description="Slide right into frame.",
        default_params={"distance_px": 180},
    ),
    "fade_in": AnimationPreset(
        id="fade_in",
        type=AnimationType.FADE_IN,
        description="Opacity ramp up.",
        default_params={"from_opacity": 0.0, "to_opacity": 1.0},
    ),
    "fade_out": AnimationPreset(
        id="fade_out",
        type=AnimationType.FADE_OUT,
        description="Opacity ramp down.",
        default_params={"from_opacity": 1.0, "to_opacity": 0.0},
    ),
    "stomp": AnimationPreset(
        id="stomp",
        type=AnimationType.STOMP,
        description="Fast downward punch and settle.",
        default_params={"distance_px": 90, "overshoot_scale": 1.08},
    ),
    "typewriter": AnimationPreset(
        id="typewriter",
        type=AnimationType.TYPEWRITER,
        description="Caption reveals characters over time.",
        default_params={},
    ),
    "word_reveal": AnimationPreset(
        id="word_reveal",
        type=AnimationType.WORD_REVEAL,
        description="Caption reveals words in sequence.",
        default_params={},
    ),
}


def get_animation_preset(preset_id: str) -> AnimationPreset | None:
    return _PRESETS.get(preset_id)


def list_animation_presets() -> list[str]:
    return sorted(_PRESETS.keys())
