"""Animation module for VASP."""

from vasp.animation.primitives import AnimationSpec, AnimationType, Keyframe
from vasp.animation.engine import AnimationEngine

__all__ = ["AnimationSpec", "AnimationType", "Keyframe", "AnimationEngine"]
