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
