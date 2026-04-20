"""Media Reader module for building serializer-ready input payloads."""

from typing import Any

from vasp.media_reader.pipeline import build_serialized_bundle, generate_input_json
from vasp.media_reader.schemas import (
    IntermediateInputPayload,
    MediaAnalysis,
    MediaContext,
    MediaInput,
    MediaProbeInfo,
    UserEditIntent,
)


def create_media_json_from_captions_file(*args: Any, **kwargs: Any):
    # Lazy import prevents runpy warning when executing `python -m vasp.media_reader.from_captions`.
    from vasp.media_reader.from_captions import create_media_json_from_captions_file as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "build_serialized_bundle",
    "generate_input_json",
    "create_media_json_from_captions_file",
    "IntermediateInputPayload",
    "MediaAnalysis",
    "MediaContext",
    "MediaInput",
    "MediaProbeInfo",
    "UserEditIntent",
]
