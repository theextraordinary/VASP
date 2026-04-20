from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlannerMatch(BaseModel):
    match_id: str
    text: str
    media_id: str
    match_strength: Literal["high", "medium", "low"] = "medium"
    match_reason: str = ""
    mandatory_media: bool = False


class PlannerUnmatchedText(BaseModel):
    text: str
    reason: str = "no suitable media"


class PlannerOutput(BaseModel):
    planner_version: str = "v3_media_text_matching"
    matches: list[PlannerMatch] = Field(default_factory=list)
    unmatched_text: list[PlannerUnmatchedText] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SegmentMedia(BaseModel):
    element_id: str
    type: str = ""
    source_path: str = ""
    about: str = ""
    aim: str = ""
    width: float | None = None
    height: float | None = None
    duration: float | None = None


class GeneratedSegment(BaseModel):
    segment_id: str
    matched_text: str
    t_start: float
    t_end: float
    media_id: str
    media: SegmentMedia
    caption_groups: list[dict[str, Any]] = Field(default_factory=list)
    user_instruction: str = ""
    warnings: list[str] = Field(default_factory=list)


class InterCanvas(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration: float
    aspect_ratio: str = "9:16"


class InterAudio(BaseModel):
    element_id: str
    source_path: str
    t_start: float = 0.0
    t_end: float
    volume: float = 1.0


class InterV3(BaseModel):
    version: str = "a2v_v3"
    canvas: InterCanvas
    background_timeline: list[dict[str, Any]] = Field(default_factory=list)
    caption_timeline: list[dict[str, Any]] = Field(default_factory=list)
    visual_timeline: list[dict[str, Any]] = Field(default_factory=list)
    audio: InterAudio | None = None
    warnings: list[str] = Field(default_factory=list)

