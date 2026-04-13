# Core Module

This folder defines the foundational data model for VASP. Core should be stable, minimal, and reusable across all pipelines.

## What Serialization Does
`serialization.py` provides helpers to convert Core objects to and from JSON. This lets us save timelines and elements, send them between modules, or store them on disk.

## What Timeline Does
`timeline.py` defines how elements are arranged over time. The Timeline holds Tracks, and each Track has TimelineItems that place an Element at a time range. This is the bridge between abstract elements and renderable structure.

## Builder and Validation (Simple)
- `builder.py` provides a lightweight `TimelineBuilder` to assemble tracks, elements, and placements without heavy abstractions.
- `validation.py` provides minimal checks such as "no overlap on the same track/layer."

## Serialization Guidelines (Element Input JSON)
All element input JSON files should follow this high-level structure:

```json
{
  "video": {
    "size": { "width": 1080, "height": 1920 },
    "fps": 30,
    "bg_color": [0, 0, 0],
    "output_path": "output/element_test.mp4"
  },
  "element": {
    "type": "caption",
    "id": "cap_1",
    "timing": { "start": 0.0, "duration": 2.0 },
    "transform": { "x": 100, "y": 200 }
  }
}
```

The serializer (`serialize_element_json`) converts these element-specific inputs into a consistent `element_json` output where the element is fully validated by Core schemas.

### Caption Input
```json
{
  "video": { "size": { "width": 1080, "height": 1920 }, "fps": 30, "bg_color": [0,0,0], "output_path": "output/caption_test.mp4" },
  "element": {
    "type": "caption",
    "id": "cap_main",
    "timing": { "start": 0.0, "duration": 3.0 },
    "transform": { "x": 100, "y": 300 },
    "text": "Hello world from VASP",
    "language": "en"
  }
}
```

### Image Input
```json
{
  "video": { "size": { "width": 1080, "height": 1920 }, "fps": 30, "bg_color": [0,0,0], "output_path": "output/image_test.mp4" },
  "element": {
    "type": "image",
    "id": "img_1",
    "timing": { "start": 0.0, "duration": 2.0 },
    "transform": { "x": 100, "y": 150 },
    "source_uri": "assets/inputs/image.jpg"
  }
}
```

### GIF Input
```json
{
  "video": { "size": { "width": 1080, "height": 1920 }, "fps": 30, "bg_color": [0,0,0], "output_path": "output/gif_test.mp4" },
  "element": {
    "type": "gif",
    "id": "gif_1",
    "timing": { "start": 0.5, "duration": 3.0 },
    "transform": { "x": 200, "y": 300 },
    "source_uri": "assets/inputs/gif.gif",
    "loop": true
  }
}
```

### Video Input
```json
{
  "video": { "size": { "width": 1080, "height": 1920 }, "fps": 30, "bg_color": [0,0,0], "output_path": "output/video_test.mp4" },
  "element": {
    "type": "video",
    "id": "vid_1",
    "timing": { "start": 0.0, "duration": 5.0 },
    "transform": { "x": 0, "y": 0 },
    "source_uri": "assets/inputs/video.mp4",
    "trim_in": 0.0,
    "trim_out": 5.0,
    "has_audio": true
  }
}
```

### Figure Input
```json
{
  "video": { "size": { "width": 1080, "height": 1920 }, "fps": 30, "bg_color": [0,0,0], "output_path": "output/figure_test.mp4" },
  "element": {
    "type": "figure",
    "id": "fig_1",
    "timing": { "start": 1.0, "duration": 2.0 },
    "transform": { "x": 400, "y": 600 },
    "figure_type": "sticker",
    "payload_uri": "assets/inputs/sticker.png"
  }
}
```

### Music Input
```json
{
  "video": { "size": { "width": 1080, "height": 1920 }, "fps": 30, "bg_color": [0,0,0], "output_path": "output/music_test.mp4" },
  "element": {
    "type": "music",
    "id": "music_1",
    "timing": { "start": 0.0, "duration": 10.0 },
    "source_uri": "assets/inputs/music.mp3",
    "loop": true,
    "volume": 0.8
  }
}
```

### Sfx Input
```json
{
  "video": { "size": { "width": 1080, "height": 1920 }, "fps": 30, "bg_color": [0,0,0], "output_path": "output/sfx_test.mp4" },
  "element": {
    "type": "sfx",
    "id": "sfx_1",
    "timing": { "start": 2.0, "duration": 1.0 },
    "source_uri": "assets/inputs/sfx.wav",
    "volume": 1.0
  }
}
```

## Element Properties (Base)
- `id`: Unique identifier for the element.
- `type`: Element type enum (image, video, caption, etc.).
- `name`: Optional human-readable label.
- `timing.start`: Start time in seconds.
- `timing.duration`: Duration in seconds.
- `transform.x`: X position.
- `transform.y`: Y position.
- `transform.scale_x`: Horizontal scale.
- `transform.scale_y`: Vertical scale.
- `transform.rotation_deg`: Rotation in degrees.
- `transform.opacity`: 0.0 to 1.0 opacity.
- `transform.anchor`: Anchor point for transforms.
- `transform.size.width`: Optional width override.
- `transform.size.height`: Optional height override.
- `transform.crop`: Optional crop box (x, y, width, height).
- `layer`: Render order within a track. Higher layer appears above lower.
- `design_ref`: Reference to a Design preset.
- `animation_ref`: Reference to an Animation preset.
- `tags`: Free-form tags for grouping or search.
- `visible`: Whether the element should render.
- `locked`: Whether editing tools should allow changes.
- `metadata`: Free-form structured data for future use.

## Caption Properties
- `text`: Caption text content.
- `language`: Optional language tag (e.g., "en").
- `max_width`: Optional width constraint for wrapping.
- `text_align`: Left/center/right alignment.
- `line_height`: Line height multiplier.
- `letter_spacing`: Extra spacing between letters.
- `wrap`: Whether to wrap text within max_width.
- `background_color`: Optional background color behind text.
- `background_opacity`: Background opacity (0-1).
- `stroke_color`: Optional outline color.
- `stroke_width`: Outline width.
- `shadow`: Optional shadow preset or CSS-like shadow string.

## Timeline Properties
- `Timeline.id`: Unique id for the timeline.
- `Timeline.tracks`: List of tracks (video, audio, overlays, captions).
- `Timeline.fps`: Frames per second.
- `Timeline.resolution`: Output resolution `(width, height)`.
- `Timeline.duration`: Total duration in seconds (can be computed).
- `Timeline.background_color`: Default background color.
- `Timeline.audio_sample_rate`: Sample rate for audio.

## Track Properties
- `Track.id`: Unique id for the track.
- `Track.type`: Track type (video, audio, overlay, caption).
- `Track.name`: Optional label for UX.
- `Track.items`: TimelineItems placed on this track.
- `Track.muted`: Whether audio is muted (audio track).
- `Track.locked`: Whether edits are blocked.

## TimelineItem Properties
- `TimelineItem.id`: Unique id for the item.
- `TimelineItem.element_id`: The Element this item places.
- `TimelineItem.track_id`: Track containing this item.
- `TimelineItem.start`: Start time in seconds.
- `TimelineItem.duration`: Duration in seconds.
- `TimelineItem.layer`: Layer within the track for stacking.
- `TimelineItem.trim_in`: Trim in time for media sources.
- `TimelineItem.trim_out`: Trim out time for media sources.
- `TimelineItem.playback_speed`: Speed multiplier.
