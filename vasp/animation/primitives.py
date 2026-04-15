from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AnimationType(str, Enum):
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    SLIDE = "slide"
    ZOOM = "zoom"
    BOUNCE = "bounce"
    SHAKE = "shake"
    POP = "pop"
    ROTATE = "rotate"
    TYPEWRITER = "typewriter"
    WORD_REVEAL = "word_reveal"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    BREATHE = "breathe"
    PULSE = "pulse"
    WIGGLE = "wiggle"
    SPIN = "spin"
    FADE = "fade"
    STOMP = "stomp"


class Keyframe(BaseModel):
    t: float = Field(..., ge=0.0)
    properties: Dict[str, float]


class AnimationSpec(BaseModel):
    id: str
    target_element_id: str
    type: AnimationType
    start: float = Field(..., ge=0.0)
    duration: float = Field(..., ge=0.0)
    easing: str = "linear"
    keyframes: List[Keyframe] = Field(default_factory=list)
    params: Optional[Dict[str, float]] = None


class AnimationPreset(BaseModel):
    """Named animation preset that Planner can reference in JSON."""

    id: str
    type: AnimationType
    description: str
    default_params: Dict[str, float] = Field(default_factory=dict)
