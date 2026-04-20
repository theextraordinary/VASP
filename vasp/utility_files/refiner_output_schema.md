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
    "duration": number
  },

  "visual_timeline": [
    {
      "element_id": "string",
      "source_ref": "string",
      "type": "video | image | gif | sticker",
      "role": "supporting_visual | accent",
      "t_start": number,
      "t_end": number,

      "layout": {
        "x": number,
        "y": number,
        "width": number,
        "height": number,
        "z_index": number,
        "opacity": number,
        "fit": "contain",
        "caption_safe": true
      },

      "transition_in": {
        "type": "fade | cut | pop",
        "duration": number
      },

      "transition_out": {
        "type": "fade | cut | pop",
        "duration": number
      },

      "animation": {
        "type": "none",
        "intensity": "low"
      },

      "audio": null,
      "reason": "string"
    }
  ],

  "caption_track": {
    "element_id": "caption_track_1",
    "sync_source": "grouped_caption_map",

    "style": {
      "font_family": "Inter",
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

  },

  "warnings": []
}

Return ONLY JSON.
No markdown.
No explanation.