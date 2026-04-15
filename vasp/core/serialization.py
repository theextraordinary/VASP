from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Type, TypeVar, Tuple, Union

from pydantic import BaseModel

from vasp.core.elements import Caption, Figure, GIF, Image, Music, Sfx, Timing, Video
from vasp.assets.semantic_library import resolve_semantic_sfx

T = TypeVar("T", bound=BaseModel)


def to_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def from_json(model_type: Type[T], payload: str) -> T:
    return model_type.model_validate_json(payload)


def serialize_element_json(input_path: Union[str, Path, dict[str, Any], BaseModel]) -> Tuple[dict[str, Any], dict[str, Any]]:
    """Normalize any input JSON to actions-over-time + element properties."""
    if isinstance(input_path, BaseModel):
        payload = input_path.model_dump()
    elif isinstance(input_path, dict):
        payload = input_path
    else:
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
        source_uri = _resolve_audio_source_uri(element)
        obj = Music(
            id=element["id"],
            timing=timing,
            source_uri=source_uri,
            loop=element.get("loop", True),
            volume=element.get("volume", 1.0),
            metadata=metadata,
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    if element_type == "sfx":
        actions = element.get("actions", [])
        timing = _timing_from_actions(actions)
        metadata = _merge_audio_metadata(element.get("metadata", {}), actions)
        source_uri = _resolve_audio_source_uri(element)
        obj = Sfx(
            id=element["id"],
            timing=timing,
            source_uri=source_uri,
            volume=element.get("volume", 1.0),
            metadata=metadata,
        )
        return _build_bundle(payload, element_id, actions, obj.model_dump())

    raise ValueError(f"Unknown element type: {element_type}")


def serialize_unified_element_json(
    input_path: Union[str, Path, dict[str, Any], BaseModel],
    *,
    drop_nulls: bool = True,
) -> dict[str, Any]:
    """Return a single serializer artifact with inline properties per element.

    Shape:
      {
        "version": "1.0",
        "video": {...},
        "elements": [
          {
            "element_id": "...",
            "type": "...",
            "about": "...",
            "aim": "...",
            "timing": {...},
            "actions": [...],
            "properties": {...}   # inline (optionally null-pruned)
          }
        ],
        "intent": {...},
        "media_context": {...}
      }
    """
    actions_json, props_json = serialize_element_json(input_path)
    return merge_serialized_bundle(actions_json, props_json, drop_nulls=drop_nulls)


def serialize_element2_json(
    input_path: Union[str, Path, dict[str, Any], BaseModel],
    *,
    drop_nulls: bool = True,
) -> dict[str, Any]:
    """Serializer v2 output: media elements + one combined caption element with word-time map."""
    actions_json, props_json = serialize_element_json(input_path)
    unified = merge_serialized_bundle(actions_json, props_json, drop_nulls=drop_nulls)
    out = _collapse_captions_to_single_element(unified)
    if drop_nulls:
        out = _drop_null_fields(out)
    out["serializer_mode"] = "v2"
    return out


def merge_serialized_bundle(
    actions_json: dict[str, Any],
    props_json: dict[str, Any],
    *,
    drop_nulls: bool = True,
) -> dict[str, Any]:
    """Merge actions + properties into a single element-centric JSON payload."""
    props_map: dict[str, dict[str, Any]] = {}
    for entry in props_json.get("elements", []):
        if not isinstance(entry, dict):
            continue
        element_id = entry.get("element_id")
        if not isinstance(element_id, str):
            continue
        props = entry.get("properties", {})
        if not isinstance(props, dict):
            props = {}
        props_map[element_id] = _drop_null_fields(props) if drop_nulls else props

    unified_elements: list[dict[str, Any]] = []
    for action_entry in actions_json.get("elements", []):
        if not isinstance(action_entry, dict):
            continue
        element_id = action_entry.get("element_id")
        if not isinstance(element_id, str):
            continue
        element_row: dict[str, Any] = {
            "element_id": element_id,
            "actions": action_entry.get("actions", []),
            "properties": props_map.get(element_id, {}),
        }
        element_row = _strip_redundant_element_fields(element_row)
        if drop_nulls:
            element_row = _drop_null_fields(element_row)
        unified_elements.append(element_row)

    unified: dict[str, Any] = {
        "version": actions_json.get("version", "1.0"),
        "video": actions_json.get("video", {}),
        "elements": unified_elements,
    }
    if "intent" in actions_json:
        unified["intent"] = actions_json["intent"]
    if "media_context" in actions_json:
        unified["media_context"] = _compact_media_context_for_unified(actions_json["media_context"])
    if drop_nulls:
        unified = _drop_null_fields(unified)
    return unified


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
            source_uri = _resolve_audio_source_uri(element)
            obj = Music(
                id=element_id,
                timing=timing,
                source_uri=source_uri,
                loop=element.get("loop", True),
                volume=element.get("volume", 1.0),
                metadata=_merge_audio_metadata(element.get("metadata", {}), actions),
                length=element.get("length"),
            )
        elif element_type == "sfx":
            source_uri = _resolve_audio_source_uri(element)
            obj = Sfx(
                id=element_id,
                timing=timing,
                source_uri=source_uri,
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

    actions_entries = []
    for eid, actions in actions_by_id.items():
        if not actions:
            continue
        source = elements_def.get(eid, {})
        metadata = source.get("metadata", {}) if isinstance(source.get("metadata", {}), dict) else {}
        actions_entries.append(
            {
                "element_id": eid,
                "type": source.get("type"),
                "about": source.get("about", metadata.get("about")),
                "aim": source.get("aim", metadata.get("aim")),
                "timing": _timing_from_actions(actions).model_dump(),
                "actions": actions,
            }
        )

    actions_json = {
        "version": "1.0",
        "video": payload["video"],
        "properties_path": None,
        "elements": actions_entries,
    }
    _attach_context(actions_json, payload)
    props_json = {"elements": elements_list}
    _attach_context(props_json, payload)
    return actions_json, props_json


def _build_bundle(
    payload: dict, element_id: str, actions: list[dict], element_dump: dict
) -> Tuple[dict[str, Any], dict[str, Any]]:
    source_element = payload.get("element", {}) if isinstance(payload.get("element", {}), dict) else {}
    metadata = source_element.get("metadata", {}) if isinstance(source_element.get("metadata", {}), dict) else {}
    actions_json = {
        "version": "1.0",
        "video": payload["video"],
        "properties_path": None,
        "elements": [
            {
                "element_id": element_id,
                "type": element_dump.get("type"),
                "about": source_element.get("about", metadata.get("about")),
                "aim": source_element.get("aim", metadata.get("aim")),
                "timing": element_dump.get("timing"),
                "actions": actions,
            }
        ],
    }
    _attach_context(actions_json, payload)
    props_json = {"elements": [{"element_id": element_id, "properties": element_dump}]}
    _attach_context(props_json, payload)
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
    elements = list(payload["elements"])
    elements.extend(_transcript_word_elements(payload))
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
            source_uri = _resolve_audio_source_uri(element)
            obj = Music(
                id=element_id,
                timing=timing,
                source_uri=source_uri,
                loop=element.get("loop", True),
                volume=element.get("volume", 1.0),
                metadata=_merge_audio_metadata(element.get("metadata", {}), actions),
            )
        elif element_type == "sfx":
            source_uri = _resolve_audio_source_uri(element)
            obj = Sfx(
                id=element_id,
                timing=timing,
                source_uri=source_uri,
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
            {
                "element_id": element_id,
                "type": element_type,
                "about": element.get("about", element.get("metadata", {}).get("about") if isinstance(element.get("metadata", {}), dict) else None),
                "aim": element.get("aim", element.get("metadata", {}).get("aim") if isinstance(element.get("metadata", {}), dict) else None),
                "timing": obj.model_dump().get("timing"),
                "actions": actions,
            }
        )
        props_entries.append({"element_id": element_id, "properties": obj.model_dump()})

    actions_json = {
        "version": "1.0",
        "video": payload["video"],
        "properties_path": None,
        "elements": actions_entries,
    }
    _attach_context(actions_json, payload)
    props_json = {"elements": props_entries}
    _attach_context(props_json, payload)
    return actions_json, props_json


def _attach_context(target: dict[str, Any], payload: dict[str, Any]) -> None:
    """Preserve upstream context (intent/media analysis) in serializer outputs."""
    if "intent" in payload:
        target["intent"] = payload["intent"]
    if "media_context" in payload:
        target["media_context"] = payload["media_context"]


def _transcript_word_elements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate caption elements from media_context transcript words (if present)."""
    media_context = payload.get("media_context", {})
    if not isinstance(media_context, dict):
        return []
    analysis = media_context.get("analysis", {})
    if not isinstance(analysis, dict):
        return []
    media_inputs = media_context.get("inputs", [])
    input_meta: dict[str, dict[str, Any]] = {}
    if isinstance(media_inputs, list):
        for item in media_inputs:
            if isinstance(item, dict) and item.get("id"):
                input_meta[str(item.get("id"))] = item

    out: list[dict[str, Any]] = []
    for media_id, block in analysis.items():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        words = transcript.get("words", [])
        if not isinstance(words, list):
            continue
        language = transcript.get("language")
        media_info = input_meta.get(str(media_id), {})
        media_aim = media_info.get("aim")
        media_about = media_info.get("about")

        for idx, raw_word in enumerate(words):
            if not isinstance(raw_word, dict):
                continue
            text = str(raw_word.get("text") or raw_word.get("word") or "").strip()
            if not text:
                continue
            start = _safe_float(raw_word.get("start"))
            end = _safe_float(raw_word.get("end"))
            if start is None:
                continue
            if end is None or end < start:
                end = start
            if end == start:
                end = start + 0.12

            out.append(
                {
                    "id": f"asr_caption_{media_id}_{idx}",
                    "type": "caption",
                    "text": text,
                    "language": language,
                    "aim": media_aim,
                    "about": media_about,
                    "transform": {"x": 540.0, "y": 1660.0},
                    "metadata": {
                        "source": "asr_whisperx",
                        "media_id": media_id,
                        "word_index": idx,
                        "aim": media_aim,
                        "about": media_about,
                        "word_features": raw_word,
                    },
                    "actions": [
                        {
                            "t_start": float(start),
                            "t_end": float(end),
                            "op": "show",
                            "params": {},
                        }
                    ],
                }
            )
    return out


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_audio_source_uri(element: dict[str, Any]) -> str:
    source_uri = element.get("source_uri")
    if source_uri:
        return str(source_uri)
    metadata = element.get("metadata", {}) if isinstance(element.get("metadata", {}), dict) else {}
    sfx_key = metadata.get("sfx_key")
    resolved = resolve_semantic_sfx(str(sfx_key) if sfx_key else None)
    if resolved is not None:
        return str(resolved)
    raise ValueError(f"Audio element '{element.get('id')}' missing source_uri and unresolved sfx_key.")


def _drop_null_fields(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            reduced = _drop_null_fields(item)
            if reduced is None:
                continue
            out[key] = reduced
        return out
    if isinstance(value, list):
        return [_drop_null_fields(item) for item in value if item is not None]
    return value


def _strip_redundant_element_fields(element_row: dict[str, Any]) -> dict[str, Any]:
    """Remove repeated payload content from unified element rows."""
    out = dict(element_row)
    props = out.get("properties")
    if not isinstance(props, dict):
        return out

    props = dict(props)
    element_id = out.get("element_id")
    if isinstance(element_id, str) and props.get("id") == element_id:
        props.pop("id", None)

    # Caption word_features duplicate text/timing heavily; keep only enrichment tags.
    metadata = props.get("metadata")
    if isinstance(metadata, dict):
        metadata = dict(metadata)
        word_features = metadata.get("word_features")
        if isinstance(word_features, dict):
            reduced = dict(word_features)
            for key in ("text", "start", "end"):
                reduced.pop(key, None)
            metadata["word_features"] = reduced
        props["metadata"] = metadata

    out["properties"] = props
    return out


def _compact_media_context_for_unified(media_context: Any) -> Any:
    """Keep media_context useful but avoid repeating heavy transcript blocks."""
    if not isinstance(media_context, dict):
        return media_context
    out = dict(media_context)
    analysis = out.get("analysis")
    if not isinstance(analysis, dict):
        return out

    compact_analysis: dict[str, Any] = {}
    for media_id, block in analysis.items():
        if not isinstance(block, dict):
            compact_analysis[media_id] = block
            continue
        block_copy = dict(block)
        transcript = block_copy.get("transcript")
        if isinstance(transcript, dict):
            t = dict(transcript)
            # Words already become caption elements in unified output.
            t.pop("words", None)
            t.pop("segments", None)
            block_copy["transcript"] = t
        compact_analysis[media_id] = block_copy
    out["analysis"] = compact_analysis
    return out


def _collapse_captions_to_single_element(unified: dict[str, Any]) -> dict[str, Any]:
    out = dict(unified)
    elements = out.get("elements", [])
    if not isinstance(elements, list):
        return out

    caption_rows: list[dict[str, Any]] = []
    non_caption_rows: list[dict[str, Any]] = []
    for row in elements:
        if not isinstance(row, dict):
            continue
        row_type = row.get("type")
        if row_type is None:
            props = row.get("properties", {})
            if isinstance(props, dict):
                row_type = props.get("type")
        if row_type == "caption":
            caption_rows.append(row)
        else:
            non_caption_rows.append(row)

    transcript_meta = _transcript_meta_from_context(out.get("media_context", {}))
    if not caption_rows and not transcript_meta:
        out["elements"] = non_caption_rows
        return out

    word_map = _word_timing_map_from_context(out.get("media_context", {}))
    if not word_map:
        word_map = _word_timing_map_from_caption_rows(caption_rows)
    if not word_map and not transcript_meta:
        out["elements"] = non_caption_rows
        return out

    if word_map:
        caption_start = min(float(w.get("start", 0.0)) for w in word_map)
        caption_end = max(float(w.get("end", caption_start)) for w in word_map)
        caption_text = " ".join(str(w.get("text", "")).strip() for w in word_map).strip()
    else:
        caption_start = 0.0
        caption_end = 0.0
        caption_text = str(transcript_meta.get("full_text", "")).strip() if isinstance(transcript_meta, dict) else ""

    first = caption_rows[0] if caption_rows else {}
    first_props = first.get("properties", {})
    if not isinstance(first_props, dict):
        first_props = {}
    props = dict(first_props)
    props["type"] = "caption"
    props["timing"] = {"start": caption_start, "duration": max(0.0, caption_end - caption_start)}
    props["text"] = caption_text
    metadata = props.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["caption_mode"] = "single_combined_element"
    metadata["word_timing_map"] = word_map
    if transcript_meta:
        metadata["transcript"] = transcript_meta
    props["metadata"] = metadata

    caption_action = {
        "t_start": caption_start,
        "t_end": caption_end,
        "op": "show",
        "params": {},
    }
    first_actions = first.get("actions", [])
    if isinstance(first_actions, list) and first_actions:
        base = first_actions[0]
        if isinstance(base, dict):
            caption_action["params"] = dict(base.get("params", {}))

    caption_element = {
        "element_id": "caption_track_1",
        "type": "caption",
        "about": first.get("about"),
        "aim": first.get("aim"),
        "timing": {"start": caption_start, "duration": max(0.0, caption_end - caption_start)},
        "actions": [caption_action],
        "properties": props,
    }

    combined = non_caption_rows + [caption_element]
    combined.sort(key=lambda r: float((r.get("timing") or {}).get("start", 0.0)))
    out["elements"] = combined
    return out


def _word_timing_map_from_context(media_context: Any) -> list[dict[str, Any]]:
    if not isinstance(media_context, dict):
        return []
    analysis = media_context.get("analysis", {})
    if not isinstance(analysis, dict):
        return []
    words: list[dict[str, Any]] = []
    idx = 0
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        for w in transcript.get("words", []) or []:
            if not isinstance(w, dict):
                continue
            text = str(w.get("text", "")).strip()
            if not text:
                continue
            start = _safe_float(w.get("start"))
            end = _safe_float(w.get("end"))
            if start is None:
                continue
            if end is None or end < start:
                end = start
            words.append(
                {
                    "index": idx,
                    "text": text,
                    "start": float(start),
                    "end": float(end),
                }
            )
            idx += 1
    words.sort(key=lambda w: float(w.get("start", 0.0)))
    for i, w in enumerate(words):
        w["index"] = i
    return words


def _word_timing_map_from_caption_rows(caption_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(caption_rows, key=lambda r: float((r.get("timing") or {}).get("start", 0.0)))
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        props = row.get("properties", {})
        text = str((props or {}).get("text", "")).strip() if isinstance(props, dict) else ""
        timing = row.get("timing", {})
        start = _safe_float((timing or {}).get("start"))
        dur = _safe_float((timing or {}).get("duration"))
        if start is None:
            actions = row.get("actions", [])
            if isinstance(actions, list) and actions:
                start = _safe_float(actions[0].get("t_start"))
                end = _safe_float(actions[0].get("t_end"))
                if start is None:
                    continue
                if end is None:
                    end = start
            else:
                continue
        else:
            end = float(start + (dur or 0.0))
        if end < start:
            end = start
        out.append(
            {
                "index": i,
                "text": text,
                "start": float(start),
                "end": float(end),
            }
        )
    return out


def _transcript_meta_from_context(media_context: Any) -> dict[str, Any]:
    if not isinstance(media_context, dict):
        return {}
    analysis = media_context.get("analysis", {})
    if not isinstance(analysis, dict):
        return {}
    full_text_parts: list[str] = []
    language: str | None = None
    segments: list[dict[str, Any]] = []
    has_transcript = False
    word_stats: dict[str, Any] = {}
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        has_transcript = True
        text = str(transcript.get("full_text", "")).strip()
        if text:
            full_text_parts.append(text)
        if language is None and transcript.get("language"):
            language = str(transcript.get("language"))
        segs = transcript.get("segments", [])
        if isinstance(segs, list):
            segments.extend([s for s in segs if isinstance(s, dict)])
        stats = transcript.get("word_stats")
        if isinstance(stats, dict):
            # Keep last observed stats block; enough for diagnostics in v2 output.
            word_stats = dict(stats)
    if not has_transcript:
        return {}
    return {
        "full_text": " ".join(full_text_parts).strip(),
        "language": language,
        "segments": segments,
        "word_stats": word_stats,
    }
