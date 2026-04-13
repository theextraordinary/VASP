from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import Field, model_validator

from vasp.schemas.base import BaseSchema


class TrackType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    OVERLAY = "overlay"
    CAPTION = "caption"


class TimelineItem(BaseSchema):
    id: str
    element_id: str
    track_id: str
    start: float = Field(..., ge=0.0)
    duration: float = Field(..., ge=0.0)
    layer: int = 0
    trim_in: float = 0.0
    trim_out: Optional[float] = None
    playback_speed: float = Field(1.0, gt=0.0)

    @property
    def end(self) -> float:
        return self.start + self.duration

    @model_validator(mode="after")
    def _validate_trim(self) -> "TimelineItem":
        if self.trim_out is not None and self.trim_out < self.trim_in:
            raise ValueError("trim_out must be >= trim_in")
        return self


class Track(BaseSchema):
    id: str
    type: TrackType
    name: Optional[str] = None
    items: List[TimelineItem] = Field(default_factory=list)
    muted: bool = False
    locked: bool = False


class Timeline(BaseSchema):
    id: str
    tracks: List[Track] = Field(default_factory=list)
    fps: int = 30
    resolution: tuple[int, int] = (1080, 1920)
    duration: float = 0.0
    background_color: str = "#000000"
    audio_sample_rate: int = 48000

    def compute_duration(self) -> float:
        max_end = 0.0
        for track in self.tracks:
            for item in track.items:
                if item.end > max_end:
                    max_end = item.end
        return max_end
