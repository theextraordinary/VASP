from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from vasp.core.elements import Caption, Figure, GIF, Image, Music, Sfx, Timing, Video

T = TypeVar("T", bound=BaseModel)


def to_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def from_json(model_type: Type[T], payload: str) -> T:
    return model_type.model_validate_json(payload)


def serialize_element_json(input_path: str) -> dict[str, Any]:
    """Normalize an element input JSON to a consistent element_json payload."""
    path = Path(input_path)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    element = payload["element"]
    element_type = element["type"]

    if element_type == "caption":
        obj = Caption(
            id=element["id"],
            timing=Timing(**element["timing"]),
            text=element["text"],
            language=element.get("language"),
            transform=element.get("transform", {}),
            metadata=element.get("metadata", {}),
        )
        return {"element": obj.model_dump(), "video": payload["video"]}

    if element_type == "image":
        obj = Image(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            transform=element.get("transform", {}),
        )
        return {"element": obj.model_dump(), "video": payload["video"]}

    if element_type == "gif":
        obj = GIF(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            loop=element.get("loop", True),
            transform=element.get("transform", {}),
        )
        return {"element": obj.model_dump(), "video": payload["video"]}

    if element_type == "video":
        obj = Video(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            trim_in=element.get("trim_in", 0.0),
            trim_out=element.get("trim_out"),
            has_audio=element.get("has_audio", True),
            transform=element.get("transform", {}),
        )
        return {"element": obj.model_dump(), "video": payload["video"]}

    if element_type == "figure":
        obj = Figure(
            id=element["id"],
            timing=Timing(**element["timing"]),
            figure_type=element.get("figure_type", "shape"),
            payload_uri=element.get("payload_uri"),
            transform=element.get("transform", {}),
        )
        return {"element": obj.model_dump(), "video": payload["video"]}

    if element_type == "music":
        obj = Music(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            loop=element.get("loop", True),
            volume=element.get("volume", 1.0),
        )
        return {"element": obj.model_dump(), "video": payload["video"]}

    if element_type == "sfx":
        obj = Sfx(
            id=element["id"],
            timing=Timing(**element["timing"]),
            source_uri=element["source_uri"],
            volume=element.get("volume", 1.0),
        )
        return {"element": obj.model_dump(), "video": payload["video"]}

    raise ValueError(f"Unknown element type: {element_type}")
