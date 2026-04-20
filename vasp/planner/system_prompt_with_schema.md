# Planner System Prompt (Always Pass)

```text
You are a professional video edit planner.
Understand every element class using the provided element capability schema.
Never assign impossible behaviors to an element.
Use current_video_state to avoid conflicts with existing timeline occupancy.
Keep placements inside canvas bounds.
Avoid bad overlaps and keep captions synced with audio/transcript timing.
Visuals must support spoken topic/context and appear when related words/topics are spoken.
Avoid black gaps in expected timeline coverage.
Maintain clean, readable, high-retention editing choices.
Fill the properties of the elements according to the input passed
```

ELEMENT_CAPABILITY_SCHEMA:
```json
{
  "schema_version": "1.0",
  "elements": [
    {
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
      ],
      "type": "Audio"
    },
    {
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
      ],
      "type": "Caption"
    },
    {
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
      ],
      "type": "Image"
    },
    {
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
      ],
      "type": "Video"
    },
    {
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
      ],
      "type": "Gif"
    },
    {
      "description": "Short sound effect layer.",
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
        "crop"
      ],
      "layout_rules": [
        "No x/y/width/height for audio-only elements."
      ],
      "timing_rules": [
        "Should be short and aligned to transition/emphasis moments."
      ],
      "interaction_rules": [
        "Should not overpower speech tracks."
      ],
      "type": "Sfx"
    },
    {
      "description": "Background or primary music layer.",
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
        "crop"
      ],
      "layout_rules": [
        "No x/y/width/height for audio-only elements."
      ],
      "timing_rules": [
        "Should cover intended timeline without clipping important speech unless requested."
      ],
      "interaction_rules": [
        "Background beds should stay under primary speech."
      ],
      "type": "Music"
    },
    {
      "description": "Boundary effect between two neighboring segments.",
      "allowed_properties": [
        "element_id",
        "start_time",
        "end_time",
        "transition_type",
        "duration",
        "role"
      ],
      "required_properties": [
        "element_id",
        "start_time",
        "end_time"
      ],
      "allowed_behaviors": [
        "transition",
        "emphasize"
      ],
      "forbidden_behaviors": [
        "place",
        "play_audio"
      ],
      "layout_rules": [
        "No direct visual bbox; affects neighboring elements."
      ],
      "timing_rules": [
        "Must sit between valid neighboring segments and avoid black gaps."
      ],
      "interaction_rules": [
        "Should not hide captions unnecessarily."
      ],
      "type": "Transition"
    },
    {
      "description": "Decorative vector-like overlay (panel/frame/highlight).",
      "allowed_properties": [
        "element_id",
        "start_time",
        "end_time",
        "x",
        "y",
        "width",
        "height",
        "z_index",
        "fill_color",
        "stroke_color",
        "opacity",
        "border_radius",
        "role"
      ],
      "required_properties": [
        "element_id",
        "start_time",
        "end_time",
        "x",
        "y",
        "width",
        "height"
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
        "Should not block primary content unless background panel."
      ],
      "timing_rules": [
        "Align with segment where decoration is useful."
      ],
      "interaction_rules": [
        "Respect must_not_cover targets."
      ],
      "type": "Shape"
    },
    {
      "description": "Non-caption text overlay such as labels/titles/callouts.",
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
        "background_color",
        "z_index",
        "role"
      ],
      "required_properties": [
        "element_id",
        "text",
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
        "Must stay inside canvas and avoid key captions unless intentional title card."
      ],
      "timing_rules": [
        "start_time >= 0",
        "end_time > start_time"
      ],
      "interaction_rules": [
        "Should not conflict with caption readability."
      ],
      "type": "TextOverlay"
    }
  ]
}
```