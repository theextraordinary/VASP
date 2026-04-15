from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from vasp.schemas.base import BaseSchema


class InterAction(BaseSchema):
    t_start: float = Field(..., ge=0.0)
    t_end: float = Field(..., ge=0.0)
    op: str = "show"
    params: dict[str, Any] = Field(default_factory=dict)


class InterElementActions(BaseSchema):
    element_id: str
    type: Optional[str] = None
    about: Optional[str] = None
    aim: Optional[str] = None
    timing: Optional[dict[str, Any]] = None
    properties: Optional[dict[str, Any]] = None
    actions: list[InterAction]


class InterRenderPlan(BaseSchema):
    """Renderer-ready plan (inter.json)."""

    version: str = "1.0"
    video: dict[str, Any]
    properties_path: Optional[str] = None
    elements: list[InterElementActions]
    updated_element_props: Optional[list[dict[str, Any]]] = None
