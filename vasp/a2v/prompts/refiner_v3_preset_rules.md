Refiner V3 Professional Preset Rules

Prefer selecting preset names instead of inventing raw styles.

Rules:
- Do not invent random colors unless creativity level is 5.
- Use dark cinematic backgrounds by default.
- Use yellow/white caption contrast often.
- Caption-only segments use center caption layout.
- Visual segments use bottom captions.
- Images should be centered cards or contained media, not stretched.
- Videos and GIFs should use visual_center_800h or visual_landscape_middle unless creativity level is 5.
- Professional edit means restrained, consistent, readable, and intentional.
- If media_id is empty, visual_timeline must be [].
- If using a preset, include the preset field names in the top-level JSON.
- Existing raw fields are allowed only for minor safe overrides.
- Choose a preset bundle first whenever possible.
- When USE PRESET BACKGROUNDS is true, choose background_image_preset from bg1, bg2, bg3, bg4, bg5.
- Use bg1 for white grid/light informative parts, bg2 for dark grid/dark informative parts, bg3 for centered visuals, bg4 for centered captions, and bg5 for white paper/light informative parts.
- If using raw overrides, use only the schema enum choices:
  - transitions: none, fade, cut, pop, slide, zoom, zoom_blur, blur_fade, whip, flash, dip
  - caption animations: word_reveal, fade, pop, slide_up, typewriter, bounce, blur_in, glow_pulse, stomp, wave_reveal, none
  - visual animations: none, subtle_zoom, subtle_zoom_out, pulse, float, drift, card_lift, tilt_float, shake
  - backgrounds: solid, gradient, vignette, blur, pattern
  - fit: contain, cover
- Prefer preset bundles for the full style policy. Individual preset fields may override the bundle only when the segment needs a local design adjustment.
- If a preset has blur_strength, glow, grain, or vignette, keep those fields so the renderer can produce the intended atmosphere.

Creativity guidance:
- creativity 0: use black_reel_canvas, bottom_subtitle_clean, visual_center_800h, caption_bottom_safe for visual segments, caption_only_center for caption-only segments.
- creativity 2: keep visual layout fixed, but choose caption/background presets.
- creativity 4 or 5: choose a full preset_bundle and vary bundles across segments when appropriate.
