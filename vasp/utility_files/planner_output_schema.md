# Planner Expected Output Schema (Plain Text)
## Hard Rules
1. Do not change any input timing, caption mapping, or element identity.
2. Use only element ids provided in input.
3. No invented timestamps.
4. Keep all placements inside 9:16 canvas.
5. Captions must remain readable and never be blocked.
6. Goal is creativity in arrangement, transitions, and emphasis — not changing source timing.
7. Ends the segements when captions ends, dont repeat captions
8. Dont overuse one element everywhere.

main_audio must be the element_id of the audio element.
main_caption must be the element_id of the caption element.

Example:
"main_audio": "media_1"
"main_caption": "caption_track_1"

---
OUTPUT SCHEMA
{
  "video_summary": {
    "theme": "string",
    "mood": "string",
    "main_audio": "media_1",
    "main_caption": "caption_track_1"
  },
  "asset_understanding": [
    {
      "element_id": "string",
      "type": "audio | caption | video | image | gif | sticker",
      "represents": "string",
      "suggested_role": "main_audio | caption | supporting_visual | accent | unused",
      "best_use": "string",
      "usefulness": "high | medium | low"
    }
  ],
  "segments": [
    {
      "segment_id": "seg_001",
      "t_start": 0.131,
      "t_end": 8.437,
      "caption_indices": [0, 1, 2, 3, 4],
      "spoken_text": "string",
      "segment_purpose": "string",
      "visual_candidates": [
        {
          "element_id": "media_2",
          "role": "supporting_visual",
          "use_for": "string",
          "time_hint": {
            "start": 0.952,
            "end": 8.437
          },
          "priority": "high | medium | low"
        }
      ],
      "caption_instruction": "string",
      "transition_intent": "none | cut | fade | zoom | pop"
    }
  ],
  "creative_suggestions": [],
  "needs_user_input": []
}

QUALITY CHECK (MUST PASS):
- [ ] All t_start/t_end values are copied from input timeline only.
- [ ] No full-screen visual overlaps another full-screen visual at same time.
- [ ] Captions are never fully covered.
- [ ] If media mismatch exists, it is listed in NEEDS USER INPUT or CREATIVE CHOICES.
- [ ] Timeline has no empty gap (caption-focused fallback is used).

VALIDATION RULES:
1. main_audio must equal an audio element_id.
2. main_caption must equal caption_track_1.
3. visual_candidates must not contain audio or caption elements.
4. role must be exactly one of: supporting_visual, accent, unused.
5. time_hint.start and time_hint.end must come from grouped_caption_map.
6. time_hint must stay inside its segment.
7. Do not use source media start_time/end_time as time_hint.
8. Segment t_start/t_end must come from caption group boundaries.
9. spoken_text must match the caption_indices timing.
10. Do not create one segment per word unless meaning changes.

Before final JSON, internally check every candidate:

candidate.element_id | segment_id | time_hint | valid?

If any candidate time_hint is outside segment, replace it with the closest matching caption boundary inside the segment.
If impossible, remove the candidate.

BAD:
segment: 0.131–8.437
candidate time_hint: 0.0–17.68

GOOD:
segment: 0.131–8.437
candidate time_hint: 0.131–8.437