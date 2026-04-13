from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class VisualStyle(BaseModel):
    fill_color: str = "#FFFFFF"
    stroke_color: Optional[str] = None
    stroke_width: float = 0.0
    shadow: Optional[str] = None
    opacity: float = Field(1.0, ge=0.0, le=1.0)


class TextStyle(BaseModel):
    font_family: str = "Inter"
    font_size: int = 48
    font_weight: str = "regular"
    color: str = "#FFFFFF"
    align: str = "center"
    line_height: float = 1.2


class DesignStyle(BaseModel):
    id: str
    name: str
    text: Optional[TextStyle] = None
    visual: Optional[VisualStyle] = None
