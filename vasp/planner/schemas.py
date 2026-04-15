from __future__ import annotations

from typing import Optional

from pydantic import Field

from vasp.schemas.base import BaseSchema


class LLM1Decision(BaseSchema):
    """High-level edit decision for a single element window."""

    element_id: str
    t_start: float = Field(..., ge=0.0)
    t_end: float = Field(..., ge=0.0)
    purpose: Optional[str] = None
    placement_zone: Optional[str] = None
    animation_ref: Optional[str] = None
    design_ref: Optional[str] = None
    caption_text: Optional[str] = None


class LLM1Plan(BaseSchema):
    """Planner output schema (llm1.json)."""

    decisions: list[LLM1Decision]
    notes: Optional[str] = None
