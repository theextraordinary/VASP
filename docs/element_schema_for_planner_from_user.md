# Element Capability Schema (Planner Learning Format)

```json
{
  "schema_version": "1.0",
  "elements": [
    {
      "type": "Audio",
      "description": "Generic timeline audio source.",
      "allowed_properties": [
        "element_id",
        "source",
        "start_time",
        "end_time",
        "volume",
        "fade_in",
        "fade_out",
        "role"
      ],
      "required_properties": [
        "element_id",
        "start_time",
        "end_time"
      ],
      "allowed_behaviors": [
        "play",
        "trim",
        "volume",
        "fade"
      ],
      "forbidden_behaviors": [
        "place",
        "move",
        "resize",
        "show",
        "hide",
        "crop",
        "rotate"
      ],
      "layout_rules": [
        "No x/y/width/height for audio-only elements."
      ],
      "timing_rules": [
        "start_time >= 0",
        "end_time > start_time",
        "end_time <= video_duration"
      ],
      "interaction_rules": [
        "May sync with captions but cannot visually occlude any element."
      ]
    },
    {
      "type": "Caption",
      "description": "On-screen transcript/caption text synced to spoken words.",
      "allowed_properties": [
        "element_id",
        "text",
        "start_time",
        "end_time",
        "x",
        "y",
        "width",
        "height",
        "font_family",
        "font_size",
        "font_weight",
        "text_color",
        "highlight_color",
        "z_index",
        "sync_reference"
      ],
      "required_properties": [
        "element_id",
        "start_time",
        "end_time"
      ],
      "allowed_behaviors": [
        "place",
        "show",
        "hide",
        "animate",
        "emphasize"
      ],
      "forbidden_behaviors": [
        "play_audio"
      ],
      "layout_rules": [
        "Must stay inside canvas.",
        "Prefer lower safe zone unless explicitly instructed."
      ],
      "timing_rules": [
        "Must not appear before spoken words.",
        "Must not remain after spoken words end.",
        "Must sync to transcript/audio map when provided."
      ],
      "interaction_rules": [
        "Must not be covered by higher z-index foreground visuals unless explicit intent."
      ]
    },
    {
      "type": "Image",
      "description": "Static visual element that can be positioned, scaled and animated.",
      "allowed_properties": [
        "element_id",
        "source",
        "start_time",
        "end_time",
        "x",
        "y",
        "width",
        "height",
        "z_index",
        "opacity",
        "crop",
        "scale",
        "rotation",
        "role",
        "content_reference"
      ],
      "required_properties": [
        "element_id",
        "start_time",
        "end_time"
      ],
      "allowed_behaviors": [
        "place",
        "show",
        "hide",
        "animate",
        "crop",
        "scale",
        "rotate",
        "trim"
      ],
      "forbidden_behaviors": [
        "play_audio",
        "rewrite_transcript"
      ],
      "layout_rules": [
        "Must stay inside canvas.",
        "Should not cover captions unless intended as background."
      ],
      "timing_rules": [
        "Should align with related topic mention when context exists."
      ],
      "interaction_rules": [
        "Respect must_not_cover constraints."
      ]
    },
    {
      "type": "Video",
      "description": "Motion visual layer used as background or foreground.",
      "allowed_properties": [
        "element_id",
        "source",
        "start_time",
        "end_time",
        "x",
        "y",
        "width",
        "height",
        "z_index",
        "opacity",
        "crop",
        "scale",
        "rotation",
        "role",
        "volume"
      ],
      "required_properties": [
        "element_id",
        "start_time",
        "end_time"
      ],
      "allowed_behaviors": [
        "place",
        "show",
        "hide",
        "animate",
        "crop",
        "scale",
        "rotate",
        "trim"
      ],
      "forbidden_behaviors": [
        "rewrite_transcript"
      ],
      "layout_rules": [
        "Background video may occupy full canvas.",
        "Foreground video must preserve caption readability."
      ],
      "timing_rules": [
        "start_time >= 0",
        "end_time > start_time",
        "end_time <= video_duration"
      ],
      "interaction_rules": [
        "If used as timeline background, avoid black gaps between segments."
      ]
    },
    {
      "type": "Gif",
      "description": "Short looping visual accent.",
      "allowed_properties": [
        "element_id",
        "source",
        "start_time",
        "end_time",
        "x",
        "y",
        "width",
        "height",
        "z_index",
        "opacity",
        "role"
      ],
      "required_properties": [
        "element_id",
        "start_time",
        "end_time"
      ],
      "allowed_behaviors": [
        "place",
        "show",
        "hide",
        "animate",
        "trim"
      ],
      "forbidden_behaviors": [
        "play_audio",
        "rewrite_transcript"
      ],
      "layout_rules": [
        "Must stay inside canvas.",
        "Avoid covering key captions."
      ],
      "timing_rules": [
        "Should align with emphasis moments or relevant topic mention."
      ],
      "interaction_rules": [
        "Use as accent, not persistent blocker."
      ]
    }
  ]
}
```
