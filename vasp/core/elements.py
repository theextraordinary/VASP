from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import Field

from vasp.schemas.base import BaseSchema


class ElementType(str, Enum):
    IMAGE = "image"
    GIF = "gif"
    CAPTION = "caption"
    VIDEO = "video"
    FIGURE = "figure"
    MUSIC = "music"
    SFX = "sfx"


class Timing(BaseSchema):
    start: float = Field(..., ge=0.0, description="Start time in seconds.")
    duration: float = Field(..., ge=0.0, description="Duration in seconds.")

    @property
    def end(self) -> float:
        return self.start + self.duration


class Size(BaseSchema):
    width: Optional[float] = Field(default=None, ge=0.0)
    height: Optional[float] = Field(default=None, ge=0.0)


class Crop(BaseSchema):
    x: float = 0.0
    y: float = 0.0
    width: Optional[float] = None
    height: Optional[float] = None


class Padding(BaseSchema):
    """Padding for text or shapes (in pixels)."""

    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    left: float = 0.0


class SourceMetadata(BaseSchema):
    """Optional metadata about the source asset."""

    mime_type: Optional[str] = None
    checksum: Optional[str] = None
    original_name: Optional[str] = None


class SourceRange(BaseSchema):
    """Optional source clip range in seconds (separate from timeline timing)."""

    start: Optional[float] = Field(default=None, ge=0.0)
    end: Optional[float] = Field(default=None, ge=0.0)


class Transform(BaseSchema):
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_deg: float = 0.0
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    anchor: Literal["center", "top_left", "top_right", "bottom_left", "bottom_right"] = "center"
    size: Size = Field(default_factory=Size)
    crop: Optional[Crop] = None
    flip_x: bool = False
    flip_y: bool = False


class Element(BaseSchema):
    id: str
    type: ElementType
    name: Optional[str] = None
    timing: Timing
    transform: Transform = Field(default_factory=Transform)
    layer: int = 0
    z_index: int = 0
    enabled: bool = True
    design_ref: Optional[str] = Field(default=None, description="Reference to Design preset.")
    animation_ref: Optional[str] = Field(default=None, description="Reference to Animation preset.")
    group_id: Optional[str] = None
    parent_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    visible: bool = True
    locked: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Image(Element):
    type: Literal[ElementType.IMAGE] = ElementType.IMAGE
    source_uri: str
    alt_text: Optional[str] = None
    source_meta: Optional[SourceMetadata] = None


class GIF(Element):
    type: Literal[ElementType.GIF] = ElementType.GIF
    source_uri: str
    loop: bool = True
    muted: bool = False
    source_range: Optional[SourceRange] = None
    source_meta: Optional[SourceMetadata] = None


class Caption(Element):
    type: Literal[ElementType.CAPTION] = ElementType.CAPTION
    text: str
    language: Optional[str] = None
    max_width: Optional[float] = None
    text_align: Literal["left", "center", "right"] = "center"
    line_height: float = Field(1.2, gt=0.0)
    letter_spacing: float = 0.0
    wrap: bool = True
    font_family: Optional[str] = None
    font_size: Optional[int] = None
    font_weight: Optional[str] = None
    color: Optional[str] = None
    padding: Padding = Field(default_factory=Padding)
    background_color: Optional[str] = None
    background_opacity: float = Field(0.0, ge=0.0, le=1.0)
    stroke_color: Optional[str] = None
    stroke_width: float = 0.0
    shadow: Optional[str] = None


class Video(Element):
    type: Literal[ElementType.VIDEO] = ElementType.VIDEO
    source_uri: str
    trim_in: float = 0.0
    trim_out: Optional[float] = None
    has_audio: bool = True
    playback_speed: float = Field(1.0, gt=0.0)
    muted: bool = False
    source_range: Optional[SourceRange] = None
    source_meta: Optional[SourceMetadata] = None


class Figure(Element):
    type: Literal[ElementType.FIGURE] = ElementType.FIGURE
    figure_type: Literal["shape", "line", "sticker", "icon"] = "shape"
    payload_uri: Optional[str] = None
    fill_color: Optional[str] = None
    stroke_color: Optional[str] = None
    stroke_width: float = 0.0
    points: Optional[list[tuple[float, float]]] = None
    text: Optional[str] = None


class Music(Element):
    type: Literal[ElementType.MUSIC] = ElementType.MUSIC
    source_uri: str
    loop: bool = True
    volume: float = Field(1.0, ge=0.0, le=1.0)
    fade_in: float = 0.0
    fade_out: float = 0.0
    muted: bool = False
    source_range: Optional[SourceRange] = None
    source_meta: Optional[SourceMetadata] = None


class Sfx(Element):
    type: Literal[ElementType.SFX] = ElementType.SFX
    source_uri: str
    volume: float = Field(1.0, ge=0.0, le=1.0)
    muted: bool = False
    source_range: Optional[SourceRange] = None
    source_meta: Optional[SourceMetadata] = None
