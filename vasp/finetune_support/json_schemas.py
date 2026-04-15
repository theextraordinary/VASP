from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class DecisionType(str, Enum):
    CAPTION = "caption"
    EMPHASIS = "emphasis"
    TRANSITION = "transition"
    ZOOM = "zoom"
    OVERLAY = "overlay"
    SFX = "sfx"
    CUT = "cut"


class CaptionPayload(BaseModel):
    text: str = Field(..., min_length=1)
    max_words: int = Field(6, ge=1, le=20)
    style: str = Field("clean")


class EmphasisPayload(BaseModel):
    words: list[str] = Field(default_factory=list)
    reason: str = Field("keyword")


class TransitionPayload(BaseModel):
    name: str = Field("cut")
    strength: float = Field(0.5, ge=0.0, le=1.0)


class ZoomPayload(BaseModel):
    level: float = Field(1.05, ge=1.0, le=2.0)
    anchor: str = Field("center")


class OverlayPayload(BaseModel):
    overlay_type: str = Field("image")
    uri: Optional[str] = None
    opacity: float = Field(1.0, ge=0.0, le=1.0)


class Decision(BaseModel):
    id: str
    type: DecisionType
    start: float = Field(..., ge=0.0)
    duration: float = Field(..., gt=0.0)
    target_element_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class A2VEditPlan(BaseModel):
    id: str
    task_type: str = Field("a2v_edit_plan")
    decisions: list[Decision] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_timings(self) -> "A2VEditPlan":
        for decision in self.decisions:
            if decision.start + decision.duration < decision.start:
                raise ValueError("Invalid timing window in decision.")
        return self


class TrainingExample(BaseModel):
    input_payload: dict[str, Any]
    output_plan: A2VEditPlan
    tags: list[str] = Field(default_factory=list)
