from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    CUT = "cut"
    ZOOM = "zoom"
    CROP = "crop"
    CAPTION = "caption"
    OVERLAY = "overlay"
    MUSIC = "music"
    SFX = "sfx"
    ANIMATION = "animation"
    DESIGN = "design"


class EditDecision(BaseModel):
    id: str
    type: DecisionType
    start: float = Field(..., ge=0.0)
    duration: float = Field(..., ge=0.0)
    target_element_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class EditPlan(BaseModel):
    id: str
    decisions: List[EditDecision] = Field(default_factory=list)
    summary: Optional[str] = None
