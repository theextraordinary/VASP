Return exactly this JSON shape:

```json
{
  "segment_id": "segment_000",
  "t_start": 0.0,
  "t_end": 3.2,
  "caption_indices": [0, 1, 2],
  "spoken_text": "exact segment transcript",
  "visual_timeline": [
    {
      "element_id": "media_5",
      "role": "supporting_visual",
      "use_for": "short reason",
      "time_hint": {
        "start": 1.2,
        "end": 2.8
      },
      "priority": "high"
    }
  ],
  "caption_instruction": "short instruction",
  "warnings": []
}
```

Validation rules:
- JSON object only, no markdown/comments.
- `visual_timeline` must be an array.
- `element_id` values must be visual assets only (no audio/caption ids).
- `time_hint.start < time_hint.end`.
- `time_hint` must be inside segment `[t_start, t_end]`.
- `time_hint` boundaries must match local caption-group boundaries.
- `caption_indices` should reference local grouped_caption_map indices only.
- Do not output layout keys (`x/y/width/height/z_index/opacity`).
