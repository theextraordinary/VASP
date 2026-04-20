# RENDERABLE OUTPUT RULE:
Every final_timeline item must include:
- element_id
- parent_element_id
- source_ref
- type
- role
- t_start
- t_end
- layout
- caption
- transition_in
- transition_out
- animation
- audio
- reason

{
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "duration": 30.035
  },
  "visual_timeline": [
    {
      "element_id": "string",
      "source_ref": "string",
      "type": "video | image | gif | sticker | audio",
      "role": "main_audio | main_visual | supporting_visual | accent",
      "t_start": "number",
      "t_end": "number",
      "layout": {
        "x": "number | null",
        "y": "number | null",
        "width": "number | null",
        "height": "number | null",
        "z_index": "number",
        "opacity": "number",
        "fit": "cover | contain | none",
        "caption_safe": "boolean"
      },
      "transition_in": {"type": "string", "duration": "number"},
      "transition_out": {"type": "string", "duration": "number"},
      "animation": {"type": "string", "intensity": "low | medium | high"},
      "audio": "object | null",
      "reason": "string"
    }
  ],
  "caption_track": {
    "element_id": "caption_track_1",
    "sync_source": "grouped_caption_map",
    "layout": {
      "x": 90,
      "y": 1450,
      "width": 900,
      "height": 300,
      "z_index": 10
    },
    "style": {
      "font_family": "Inter",
      "font_size_rule": "1-3 words: 70, 4-7 words: 62, 8+ words: 56",
      "font_weight": "800",
      "text_color": "#FFFFFF",
      "highlight_color": "#FFD84D",
      "background_color": "rgba(0,0,0,0.45)",
      "align": "center",
      "vertical_align": "middle"
    },
    "animation": {
      "type": "word_reveal",
      "intensity": "medium"
    },
    "cues": [
      {
        "index": "number",
        "text": "exact caption text",
        "t_start": "number",
        "t_end": "number"
      }
    ]
  },
  "warnings": []
}

For caption:
- final_timeline must contain one caption item per caption group inside the segment.
- element_id format: caption_track_1_group_{index}
- parent_element_id: caption_track_1
- source_ref: null
- caption.text must be exact grouped_caption_map[index].text
- t_start/t_end must exactly match that caption group.

For non-caption:
- caption must be null.

For non-audio:
- audio must be null.

For audio:
- layout.x/y/width/height = null
- layout.fit = "none"
- caption = null.

COMPACT CAPTION RULE:
Do not create one full final_timeline object per caption.
Create one caption_track object with shared layout/style/animation.
Inside it, output only cues:
{index, text, t_start, t_end}
The text must be the exact caption group text.

VISUAL VALIDATION:
If visual does not overlap caption box, caption_safe must be true.
If supporting_visual lasts longer than 4 seconds, shorten it to the strongest matching phrase window.

For audio:
- layout.x/y/width/height = null
- layout.fit = "none"
- audio.volume must be provided

For caption:
- source_ref = null
- caption.text must be exact caption group text
- caption.caption_group_index must match grouped_caption_map index
- layout.z_index should be highest
- layout.caption_safe = true

For video/image/gif/sticker:
- caption fields should be null
- source_ref must be element_id or real source path
- layout must stay inside canvas
