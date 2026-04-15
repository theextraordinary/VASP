"""Animation module for VASP."""

from vasp.animation.catalog import get_animation_preset, list_animation_presets
from vasp.animation.primitives import AnimationPreset, AnimationSpec, AnimationType, Keyframe
from vasp.animation.engine import AnimationEngine, BasicAnimationEngine
from vasp.animation.presets import expand_animation_actions

__all__ = [
    "AnimationPreset",
    "AnimationSpec",
    "AnimationType",
    "Keyframe",
    "AnimationEngine",
    "BasicAnimationEngine",
    "expand_animation_actions",
    "get_animation_preset",
    "list_animation_presets",
]
