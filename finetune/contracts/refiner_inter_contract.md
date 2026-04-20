# Refiner `inter.json` Contract (Week 1)

Refiner must return a single valid JSON object.

Top-level required keys:

- `version`
- `video`
- `elements`

`video` required keys:

- `size.width`
- `size.height`
- `fps`
- `output_path`

`elements` rules:

- Must be an array of objects.
- Every element must include:
  - `element_id`
  - `type`
  - `timing`
  - `actions`
  - `properties`
- `actions` must be sorted by `t_start` ascending.
- For `caption_track_1`, actions must be non-overlapping in time.

Planner correspondence rules:

- If planner says `Elements Used` includes an id, that id must exist in `elements`.
- If planner includes `audio_1`, refiner must include an audio element with playable action.
- Caption style/placement directives from planner must appear in caption action params (font/placement/stroke/background as applicable).

Output restrictions:

- No markdown fences.
- No commentary text outside the JSON object.
- No missing required keys.
