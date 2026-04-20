# Semantic Grounding Pair Template (Planner -> Refiner)

Use this template to create **high-quality paired training rows** where the model learns:
- what an element represents (`about`)
- why it should be used (`aim`)
- when it should appear (caption-time alignment)
- where it should be placed (safe, readable, contextual)

## 1) Planner Row Template (`planner_*`)

```json
{
  "task": "planner_edit_plan",
  "id": "planner_semantic_grounding_XXX",
  "messages": [
    {
      "role": "system",
      "content": "You are VASP Planner. Return ONLY EDIT PLAN text with exact headings. No JSON. No markdown."
    },
    {
      "role": "user",
      "content": "Task: Generate a structured language edit plan for a short-form video. User Instruction: <STYLE + INTENT>. Goal: Create a smooth, engaging, high-retention edit using the provided elements. Priority Order: [Audio, Caption, Image, Video, Sfx, Gif] Rules: <YOUR STANDARD RULE BLOCK> Elements:\n<PASTE element2_compact.txt CONTENT>"
    },
    {
      "role": "assistant",
      "content": "EDIT PLAN\nGlobal Style: <...>\nAudio Decision: <...>\nCaption Style: <...>\nVisual Style: <...>\nBackground Style: <...>\nSegmentation Rule: <...>\nSegment 1\nTime: <start-end>\nPurpose: <semantic purpose>\nElements Used: <audio_x, caption_track_1, image_y>\nCaption Decision: <grouping + important words>\nVisual Decision: Show <image_y> when caption mentions <entity phrase> because about='<...>' and aim='<...>'.\nAnimation Decision: <renderer-supported animation>\nPlacement Decision: <x/y region + why it preserves caption readability>\nTiming Events:\n- time: <t> event: <entity mention -> image in>\n- time: <t> event: <topic shift -> image out>\nTransition Out: <light transition>\nEngagement Note: <...>\nSegment 2\n..."
    }
  ]
}
```

Planner gold output **must** explicitly include:
- semantic match reason (`about` / `aim` -> use decision)
- placement reason (why this region)
- timing reason (spoken entity -> show/hide)

---

## 2) Refiner Row Template (`refiner_*`)

```json
{
  "task": "refiner_inter",
  "id": "refiner_semantic_grounding_XXX",
  "messages": [
    {
      "role": "system",
      "content": "You are VASP Refiner. Return ONLY strict inter.json."
    },
    {
      "role": "user",
      "content": "USER_INSTRUCTION:\n<same instruction>\n\nPLANNER_TEXT:\n<PASTE exact planner gold output>\n\nELEMENT_COMPACT:\n<PASTE element2_compact.txt CONTENT>\n\nReturn only valid inter.json."
    },
    {
      "role": "assistant",
      "content": "{ \"version\": \"1.1\", \"video\": { ... }, \"elements\": [ ... ] }"
    }
  ]
}
```

Refiner gold output **must** enforce:
- only known element IDs from element compact
- image action timing aligned to planner semantic event times
- caption actions contiguous and in sync with word map
- safe screen placement (captions lower safe zone)
- no duplicated highlight layers for same word

---

## 3) Hard-Negative Design (for DPO / rejection data)

For each positive pair, create 1-3 rejected variants:
- wrong element timing (early/late)
- wrong placement (covers caption)
- wrong semantic match (image shown on unrelated phrase)
- wrong grouping boundaries (crosses sentence/long pause)

Store as DPO rows:

```json
{
  "id": "dpo_refiner_semantic_grounding_XXX",
  "task": "refiner_dpo",
  "prompt": "<same refiner user prompt>",
  "chosen": "<gold inter.json>",
  "rejected": "<bad but plausible inter.json>"
}
```

