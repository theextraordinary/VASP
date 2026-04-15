# Media Reader

The Media Reader is the **pre-serialization** stage. It takes a user instruction and one or more media paths, probes basic metadata, and builds an **intermediate JSON** that the existing serializer already understands.

It **does not** render video and **does not** replace the serializer or renderer.

## What It Does (MVP)

1. **Detects media type** from file extension.
2. **Probes basic metadata** (duration, width/height, fps, audio channels/sample rate) using `ffprobe` if available.
3. **Builds a media context** for the input.
4. **Generates serializer-ready input JSON** (elements + actions).
5. **Optionally transcribes audio/video via WhisperX** and stores enriched caption context at
   `media_context.analysis[media_id].transcript`.

No AI or heavy analysis is used. All behavior is rule-based and safe.

## How It Decides “What Media Is About”

By default it stays deterministic and local:
- Detects the **type** by file extension.
- Reads **technical metadata** via `ffprobe`.
- For audio-bearing inputs, attempts WhisperX transcription and deterministic word tagging.

This is intentional for the MVP. Later, we can plug in **Gemma-based analysis** in `vasp/media_reader/analyzers.py` to add semantic summaries or tags.

## Main API

### `generate_input_json(...)`
Builds a serializer-ready JSON payload.

```python
from vasp.media_reader import generate_input_json

payload = generate_input_json(
    instruction="make this dramatic with captions",
    media_paths=["assets/inputs/video.mp4"],
    output_path="output/final.mp4",
    options={
        "asr_enabled": True,
        "asr_model_size": "small",
        "instruction_1": "prioritize spoken keywords",
        "instruction_2": "keep caption pacing tight",
        "instruction_3": "highlight pauses for emphasis",
    },
)
```

### `build_serialized_bundle(...)`
Runs Media Reader and immediately feeds into serializer.

```python
from vasp.media_reader import build_serialized_bundle

actions_json, props_json = build_serialized_bundle(
    instruction="simple clean edit",
    media_paths=["assets/inputs/video.mp4", "assets/inputs/music.mp3"],
    output_path="output/final.mp4",
)
```

## How To Run End-to-End (Manual)

```python
from vasp.media_reader import generate_input_json
from vasp.core.serialization import serialize_element_json
from vasp.render.element_renderer import render_from_json

payload = generate_input_json(
    instruction="make it clean and bold",
    media_paths=["assets/inputs/video.mp4"],
    output_path="output/final.mp4",
)

actions_json, props_json = serialize_element_json(payload)
actions_path = "output/elements.json"
props_path = "output/elementsProps.json"
actions_json["properties_path"] = props_path

import json
with open(actions_path, "w", encoding="utf-8") as f:
    json.dump(actions_json, f, indent=2)
with open(props_path, "w", encoding="utf-8") as f:
    json.dump(props_json, f, indent=2)

render_from_json(actions_path, strict=True)
```

## Notes

- If `ffprobe` is not available, probing gracefully returns empty metadata.
- The Media Reader output is **serializer compatible** and does not introduce a new render contract.
- You can keep using existing manual JSON fixtures — Media Reader is purely additive.
