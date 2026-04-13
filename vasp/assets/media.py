from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class MediaType(str, Enum):
    IMAGE = "image"
    GIF = "gif"
    VIDEO = "video"
    AUDIO = "audio"
    FIGURE = "figure"


class MediaAsset(BaseModel):
    id: str
    type: MediaType
    uri: str
    name: Optional[str] = None
    tags: list[str] = []
