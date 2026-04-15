from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from vasp.schemas.base import BaseSchema


class UserEditIntent(BaseSchema):
    """Lightweight user intent for upstream planning and templating."""

    instruction: str
    style: Optional[str] = None
    tone: Optional[str] = None
    notes: Optional[str] = None
    target_aspect_ratio: Optional[str] = None
    caption_enabled: bool = True
    zoom_style: Optional[str] = None
    meme_style: Optional[str] = None


class MediaInput(BaseSchema):
    """Incoming media reference from the user."""

    id: str
    path: str
    media_type: Literal["video", "image", "audio", "gif", "music", "sfx"]
    role: Optional[str] = None
    aim: Optional[str] = None
    about: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class MediaProbeInfo(BaseSchema):
    """Basic media metadata discovered by probing."""

    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    audio_channels: Optional[int] = None
    sample_rate: Optional[int] = None


class MediaAnalysis(BaseSchema):
    """Optional analysis hooks for later stages."""

    # Backward-compatible: can hold legacy list format or richer dict payload.
    transcript: Optional[Any] = None
    silence_regions: Optional[list[dict[str, Any]]] = None
    scene_boundaries: Optional[list[dict[str, Any]]] = None
    keyframes: Optional[list[dict[str, Any]]] = None
    media_tags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: Optional[str] = None


class MediaContext(BaseSchema):
    """Aggregated media context used to enrich serializer input."""

    inputs: list[MediaInput]
    probe: dict[str, MediaProbeInfo] = Field(default_factory=dict)
    analysis: dict[str, MediaAnalysis] = Field(default_factory=dict)


class IntermediateInputPayload(BaseSchema):
    """Serializer-ready input enriched with media context."""

    intent: UserEditIntent
    media_context: MediaContext
    video: dict[str, Any]
    elements: list[dict[str, Any]]
