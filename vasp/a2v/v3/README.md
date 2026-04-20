# A2V Pipeline V3

Pipeline v3 separates media selection, timing, styling, and rendering.

## Overview

1. `media.json` is created from `captions.txt` using existing VASP media reader logic.
2. Planner matches visual media to exact transcript text spans.
3. `segment_generator.py` recovers timing from caption groups / word timing and creates one segment per match.
4. Refiner styles each segment without changing timing or media ID.
5. `inter_generator.py` combines refined segments into `inter.json`.
6. `render_into_video.py` renders `insta_edit.mp4`.

## Design

- Planner matches media to transcript text only.
- Segment generator handles timing.
- Refiner styles but does not change timing.
- Inter generator combines refined outputs.
- Renderer renders `inter.json` directly.

## Outputs

Each run writes:

- `media.json`
- `planner_prompt.txt`
- `planner_output.raw.txt`
- `planner_output.json`
- `generated_segments/`
- `refiner_inputs/`
- `refiner_outputs/`
- `inter.json`
- `insta_edit.mp4`

## CLI

```bash
python -m vasp.a2v.v3.new_flow_pipeline_v3 \
  --edit-name "edit_v3" \
  --captions-file "assets/inputs/edit2/captions.txt" \
  --instruction "Create a clean engaging short-form video with synced captions." \
  --planner-endpoint "https://example.ngrok-free.dev/planner/generate" \
  --refiner-endpoint "https://example.ngrok-free.dev/refiner/generate"
```

## UI

Install the optional UI dependency:

```bash
pip install -e ".[ui]"
```

Launch the MVP studio:

```bash
python -m vasp.a2v.v3.ui
```

The UI writes uploaded files to `assets/inputs/{edit_name}/`, creates or accepts a `captions.txt`, calls the existing V3 pipeline, and returns `insta_edit.mp4`.

## Prompts

- `prompts/planner_sp.md`: planner role and matching rules.
- `prompts/planner_prompt.md`: prompt body template with transcript and media lists.
- `prompts/planner_os.md`: planner JSON output schema.
- `prompts/refiner_sp.md`: refiner role and styling rules.
- `prompts/refiner_os.md`: refiner JSON output schema.
