Refiner output schema:

PRESET SELECTION IS REQUIRED.
Every output must choose preset names from AVAILABLE REFINER PRESETS.
Do not invent preset names.
Use preset names as the main style policy for the whole segment.
Only include raw layout/style/background fields when a small safe override is necessary.

Style selection hierarchy:
0. USER INSTRUCTION has priority over default style preferences and preset recommendations. If the user asks for a particular style, mood, caption behavior, animation level, or says to avoid a design choice, choose presets and overrides that satisfy that instruction first.
1. Prefer one top-level preset_bundle for the whole segment.
2. Fill the explicit top-level preset fields below. They may come from the bundle or override the bundle with another valid preset name.
3. Timeline items should normally inherit from those presets.
4. If a timeline item needs a small override, use only the enum choices shown in this schema.
5. Do not invent new animation, transition, background, media, or layout types.

Hard constraints still apply even when following USER INSTRUCTION:
- valid JSON only
- preserve segment_id, t_start, t_end, media_id/source_ref
- do not invent preset names or media ids
- keep captions readable and inside canvas unless the user explicitly requests no captions
- keep visual_timeline empty for caption-only/unmatched segments
- never create empty visual items

Required top-level preset fields:
- preset_bundle
- background_preset
- background_image_preset
- caption_preset
- caption_layout_preset
- visual_layout_preset
- caption_animation_preset
- visual_animation_preset
- transition_preset


Allowed raw override enums:
- background_timeline.type: "solid | gradient | vignette | blur | pattern"
- background_image_preset: "bg1 | bg2 | bg3 | bg4 | bg5"
- visual_timeline.type: "video | image | gif | sticker"
- transition_in.type / transition_out.type: "none | fade | cut | pop | slide | zoom | zoom_blur | blur_fade | whip | flash | dip"
- transition_in.direction / transition_out.direction for slide/whip: "up | down | left | right"
- caption animation.type: "word_reveal | fade | pop | slide_up | typewriter | bounce | blur_in | glow_pulse | stomp | wave_reveal | none"
- visual animation.type: "none | subtle_zoom | subtle_zoom_out | pulse | float | drift | card_lift | tilt_float | shake"
- animation.intensity: "low | medium | high"
- layout.fit: "contain | cover"
- caption align: "left | center | right"

{
  "segment_id": "segment_001",
  "creativity_level": 2,
  "preset_bundle": "science_discovery",
  "background_preset": "neon_science_blue",
  "background_image_preset": "bg2",
  "caption_preset": "science_clean_blue",
  "caption_layout_preset": "caption_bottom_safe",
  "visual_layout_preset": "visual_center_800h",
  "caption_animation_preset": "caption_slide_up_clean",
  "visual_animation_preset": "visual_slow_zoom_in",
  "transition_preset": "soft_fade",
  "style_policy": {
    "visual_layout_mode": "...",
    "caption_layout_mode": "...",
    "caption_style_mode": "...",
    "animation_mode": "...",
    "transition_mode": "...",
    "background_mode": "..."
  },
  "t_start": 1.392,
  "t_end": 5.014,
  "background_timeline": [
    {
      "t_start": 1.392,
      "t_end": 5.014,
      "preset": "neon_science_blue",
      "background_image_preset": "bg2",
      "reason": "preset:neon_science_blue",
      "override": {
        "type": "solid | gradient | vignette | blur | pattern",
        "color": "#000000",
        "secondary_color": "#111827",
        "opacity": 1.0,
        "grain": 0.0,
        "vignette": 0.0,
        "blur_strength": 0.0,
        "glow": 0.0
      }
    }
  ],
  "caption_timeline": [
    {
      "caption_group_index": 2,
      "text": "exact caption text",
      "t_start": 1.392,
      "t_end": 2.752,
      "highlight_words": [],
      "caption_preset": "science_clean_blue",
      "caption_layout_preset": "caption_bottom_safe",
      "caption_animation_preset": "caption_slide_up_clean",
      "animation_override": {
        "type": "word_reveal | fade | pop | slide_up | typewriter | bounce | blur_in | glow_pulse | stomp | wave_reveal | none",
        "intensity": "low | medium | high"
      },
      "style_override": {
        "font_family": "Inter | Montserrat | Poppins | Bebas Neue",
        "font_size": 56,
        "font_weight": "700 | 800 | 900",
        "text_color": "#FFFFFF",
        "highlight_color": "#FFD84D",
        "background_color": "rgba(0,0,0,0.0)",
        "align": "left | center | right"
      },
      "preset_note": "caption style/layout/animation resolved from caption_preset, caption_layout_preset, caption_animation_preset; override fields are optional"
    }
  ],
  "visual_timeline": [
    {
      "element_id": "media_5",
      "source_ref": "media_5",
      "type": "video | image | gif | sticker",
      "t_start": 1.392,
      "t_end": 5.014,
      "visual_layout_preset": "visual_center_800h",
      "visual_animation_preset": "visual_slow_zoom_in",
      "transition_preset": "soft_fade",
      "transition_in": {
        "type": "none | fade | cut | pop | slide | zoom | zoom_blur | blur_fade | whip | flash | dip",
        "direction": "up | down | left | right",
        "duration": 0.15
      },
      "transition_out": {
        "type": "none | fade | cut | pop | slide | zoom | zoom_blur | blur_fade | whip | flash | dip",
        "direction": "up | down | left | right",
        "duration": 0.15
      },
      "animation_override": {
        "type": "none | subtle_zoom | subtle_zoom_out | pulse | float | drift | card_lift | tilt_float | shake",
        "intensity": "low | medium | high"
      },
      "layout_override": {
        "fit": "contain | cover"
      },
      "preset_note": "visual layout/transition/animation resolved from visual_layout_preset, transition_preset, visual_animation_preset; override fields are optional"
    }
  ],
  "warnings": []
}
