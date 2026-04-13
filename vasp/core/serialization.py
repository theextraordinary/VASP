from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Type, TypeVar, Tuple

from pydantic import BaseModel

from vasp.core.elements import Caption, Figure, GIF, Image, Music, Sfx, Timing, Video

T = TypeVar("T", bound=BaseModel)


def to_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def from_json(model_type: Type[T], payload: str) -> T:
    return model_type.model_validate_json(payload)


def serialize_element_json(input_path: str) -> Tuple[dict[str, Any], dict[str, Any]]:
    """Normalize any input JSON to actions-over-time + element properties."""
    path = Path(input_path)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if "segments" in payload:
        return _serialize_segment_schema(payload)

    if "elements" in payload:
        return _serialize_multi_elements(payload)

    if "element" not in payload:
        raise ValueError("Input JSON must contain 'element' or 'elements'.")
    element = payload["element"]
    element_type = element["type"]
    element_id = element["id"]

    if element_type == "caption":
        actions = element.get("actions", [])
        timing = _timing_from_actions(actions)
        obj = Caption(
            id=element["id"],
            timing=timing,
            text=element["text"],
            language=element.get("language"),
            transform=element.get("transform", {}),
            metadata=element.get("metadata", {}),
        )
        if not actions:
            actions = [
                {
                    "t_start": obj.timing.start,
                    "t_end": obj.timing.end,
                    "op": "word_scatter_color",
                    "params": {"seed": 42},
                }
            ]
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    if element_type == "image":
        actions = element.get("actions", [])
        if not actions:
            actions = _actions_from_instructions(element.get("metadata", {}))
        timing = _timing_from_actions(actions)
        obj = Image(
            id=element["id"],
            timing=timing,
            source_uri=element["source_uri"],
            transform=element.get("transform", {}),
            metadata=element.get("metadata", {}),
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    if element_type == "gif":
        actions = element.get("actions", [])
        timing = _timing_from_actions(actions)
        obj = GIF(
            id=element["id"],
            timing=timing,
            source_uri=element["source_uri"],
            loop=element.get("loop", True),
            transform=element.get("transform", {}),
            metadata=element.get("metadata", {}),
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    if element_type == "video":
        actions = element.get("actions", [])
        timing = _timing_from_actions(actions)
        obj = Video(
            id=element["id"],
            timing=timing,
            source_uri=element["source_uri"],
            trim_in=element.get("trim_in", 0.0),
            trim_out=element.get("trim_out"),
            has_audio=element.get("has_audio", True),
            transform=element.get("transform", {}),
            metadata=element.get("metadata", {}),
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    if element_type == "figure":
        actions = element.get("actions", [])
        timing = _timing_from_actions(actions)
        obj = Figure(
            id=element["id"],
            timing=timing,
            figure_type=element.get("figure_type", "shape"),
            payload_uri=element.get("payload_uri"),
            transform=element.get("transform", {}),
            metadata=element.get("metadata", {}),
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    if element_type == "music":
        actions = element.get("actions", [])
        timing = _timing_from_actions(actions)
        metadata = _merge_audio_metadata(element.get("metadata", {}), actions)
        obj = Music(
            id=element["id"],
            timing=timing,
            source_uri=element["source_uri"],
            loop=element.get("loop", True),
            volume=element.get("volume", 1.0),
            metadata=metadata,
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    if element_type == "sfx":
        actions = element.get("actions", [])
        timing = _timing_from_actions(actions)
        metadata = _merge_audio_metadata(element.get("metadata", {}), actions)
        obj = Sfx(
            id=element["id"],
            timing=timing,
            source_uri=element["source_uri"],
            volume=element.get("volume", 1.0),
            metadata=metadata,
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    raise ValueError(f"Unknown element type: {element_type}")


def _serialize_segment_schema(payload: dict) -> Tuple[dict[str, Any], dict[str, Any]]:
    elements_def = payload.get("elements", {})
    segments = payload.get("segments", [])
    if not elements_def or not segments:
        raise ValueError("Segment schema requires 'elements' and 'segments'.")

    # Normalize elements_def to dict
    if isinstance(elements_def, list):
        elements_def = {item["id"]: item for item in elements_def}

    actions_by_id: dict[str, list[dict]] = {eid: [] for eid in elements_def.keys()}

    for segment in segments:
        seg_start = float(segment.get("t_start", 0.0))
        seg_end = float(segment.get("t_end", seg_start))
        for entry in segment.get("elements", []):
            ref = entry.get("ref") or entry.get("element_id")
            if not ref:
                continue
            if ref not in actions_by_id:
                actions_by_id[ref] = []
            entry_actions = entry.get("actions") or []
            if not entry_actions:
                entry_actions = [{"op": "show"}]
            for action in entry_actions:
                op = action.get("op", "show")
                a_start = float(action.get("t_start", 0.0))
                a_end = action.get("t_end")
                if a_end is None:
                    a_end = seg_end - seg_start
                a_end = float(a_end)
                abs_start = seg_start + a_start
                abs_end = seg_start + a_end
                params = action.get("params", {})
                actions_by_id[ref].append(
                    {
                        "t_start": abs_start,
                        "t_end": abs_end,
                        "op": op,
                        "params": params,
                    }
                )

    # Build element objects
    elements_list = []
    for element_id, element in elements_def.items():
        element_type = element["type"]
        actions = actions_by_id.get(element_id, [])
        if not actions:
            # Element never appears in any segment; skip to keep timing derivation valid.
            continue
        timing = _timing_from_actions(actions)

        if element_type == "image":
            obj = Image(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        elif element_type == "gif":
            obj = GIF(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                loop=element.get("loop", True),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        elif element_type == "video":
            obj = Video(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                trim_in=element.get("trim_in", 0.0),
                trim_out=element.get("trim_out"),
                has_audio=element.get("has_audio", True),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
                length=element.get("length"),
            )
        elif element_type == "figure":
            obj = Figure(
                id=element_id,
                timing=timing,
                figure_type=element.get("figure_type", "shape"),
                payload_uri=element.get("payload_uri"),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        elif element_type == "music":
            obj = Music(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                loop=element.get("loop", True),
                volume=element.get("volume", 1.0),
                metadata=_merge_audio_metadata(element.get("metadata", {}), actions),
                length=element.get("length"),
            )
        elif element_type == "sfx":
            obj = Sfx(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                volume=element.get("volume", 1.0),
                metadata=_merge_audio_metadata(element.get("metadata", {}), actions),
                length=element.get("length"),
            )
        elif element_type == "caption":
            obj = Caption(
                id=element_id,
                timing=timing,
                text=element.get("text", ""),
                language=element.get("language"),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        else:
            raise ValueError(f"Unknown element type: {element_type}")

        elements_list.append({"element_id": element_id, "properties": obj.model_dump()})

    actions_entries = [
        {"element_id": eid, "timing": _timing_from_actions(actions).model_dump(), "actions": actions}
        for eid, actions in actions_by_id.items()
        if actions
    ]

    actions_json = {
        "version": "1.0",
        "video": payload["video"],
        "properties_path": None,
        "elements": actions_entries,
    }
    props_json = {"elements": elements_list}
    return actions_json, props_json


def _build_bundle(
    payload: dict, element_id: str, actions: list[dict], element_dump: dict
) -> Tuple[dict[str, Any], dict[str, Any]]:
    actions_json = {
        "version": "1.0",
        "video": payload["video"],
        "properties_path": None,
        "elements": [{"element_id": element_id, "timing": element_dump.get("timing"), "actions": actions}],
    }
    props_json = {"elements": [{"element_id": element_id, "properties": element_dump}]}
    return actions_json, props_json


def _actions_from_instructions(metadata: dict) -> list[dict]:
    instructions = metadata.get("instructions") if isinstance(metadata, dict) else None
    if not instructions:
        return []
    actions: list[dict] = []
    for instr in instructions:
        base = {
            "t_start": instr.get("t_start", 0.0),
            "t_end": instr.get("t_end", 0.0),
        }
        if "crop" in instr:
            actions.append({**base, "op": "crop", "params": instr["crop"]})
        if "padding" in instr:
            actions.append({**base, "op": "pad", "params": instr["padding"]})
    return actions


def _timing_from_actions(actions: list[dict]) -> Timing:
    if not actions:
        raise ValueError("actions are required to derive timing when timing is omitted.")
    starts = [float(a.get("t_start", 0.0)) for a in actions]
    ends = [float(a.get("t_end", 0.0)) for a in actions]
    start = min(starts)
    end = max(ends)
    return Timing(start=start, duration=max(0.0, end - start))


def _merge_audio_metadata(metadata: dict, actions: list[dict]) -> dict:
    base = dict(metadata) if isinstance(metadata, dict) else {}
    for action in actions:
        params = action.get("params", {})
        if params.get("crop_loudest"):
            base["crop_loudest"] = True
        if "volume" in params:
            base.setdefault("volume", params.get("volume"))
    return base


def _serialize_multi_elements(payload: dict) -> Tuple[dict[str, Any], dict[str, Any]]:
    elements = payload["elements"]
    actions_entries: list[dict] = []
    props_entries: list[dict] = []
    intervals: dict[str, tuple[float, float]] = {}
    layers: dict[str, int] = {}

    def _interval_from_actions_or_timing(el: dict) -> tuple[float, float]:
        actions = el.get("actions", [])
        if actions:
            starts = [float(a.get("t_start", 0.0)) for a in actions]
            ends = [float(a.get("t_end", 0.0)) for a in actions]
            return (min(starts), max(ends))
        timing = el.get("timing", {})
        start = float(timing.get("start", 0.0))
        duration = float(timing.get("duration", 0.0))
        return (start, start + duration)

    def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
        return a[0] < b[1] and b[0] < a[1]

    # First pass: compute intervals.
    for element in elements:
        intervals[element["id"]] = _interval_from_actions_or_timing(element)

    # Second pass: assign layers based on overlap and order in input.
    for idx, element in enumerate(elements):
        element_id = element["id"]
        layer = 0
        for prev in elements[:idx]:
            prev_id = prev["id"]
            if _overlaps(intervals[element_id], intervals[prev_id]):
                layer = max(layer, layers.get(prev_id, 0) + 1)
        layers[element_id] = layer
    for element in elements:
        element_type = element["type"]
        element_id = element["id"]
        actions = element.get("actions", [])
        if not actions:
            actions = _actions_from_instructions(element.get("metadata", {}))
        timing = _timing_from_actions(actions)

        if element_type == "image":
            obj = Image(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        elif element_type == "gif":
            obj = GIF(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                loop=element.get("loop", True),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        elif element_type == "video":
            obj = Video(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                trim_in=element.get("trim_in", 0.0),
                trim_out=element.get("trim_out"),
                has_audio=element.get("has_audio", True),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        elif element_type == "figure":
            obj = Figure(
                id=element_id,
                timing=timing,
                figure_type=element.get("figure_type", "shape"),
                payload_uri=element.get("payload_uri"),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        elif element_type == "music":
            obj = Music(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                loop=element.get("loop", True),
                volume=element.get("volume", 1.0),
                metadata=_merge_audio_metadata(element.get("metadata", {}), actions),
            )
        elif element_type == "sfx":
            obj = Sfx(
                id=element_id,
                timing=timing,
                source_uri=element["source_uri"],
                volume=element.get("volume", 1.0),
                metadata=_merge_audio_metadata(element.get("metadata", {}), actions),
            )
        elif element_type == "caption":
            obj = Caption(
                id=element_id,
                timing=timing,
                text=element["text"],
                language=element.get("language"),
                transform=element.get("transform", {}),
                metadata=element.get("metadata", {}),
            )
        else:
            raise ValueError(f"Unknown element type: {element_type}")

        obj.layer = layers.get(element_id, 0)
        actions_entries.append(
            {"element_id": element_id, "timing": obj.model_dump().get("timing"), "actions": actions}
        )
        props_entries.append({"element_id": element_id, "properties": obj.model_dump()})

    actions_json = {
        "version": "1.0",
        "video": payload["video"],
        "properties_path": None,
        "elements": actions_entries,
    }
    props_json = {"elements": props_entries}
    return actions_json, props_json
