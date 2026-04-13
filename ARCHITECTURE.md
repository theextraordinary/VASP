# VASP Architecture Document

## 1. Executive Summary
VASP is a modular, timeline‑first AI video editing framework. The architecture separates **representation (Core)**, **appearance (Design)**, **motion (Animation)**, **decision‑making (Edit)**, and **workflow orchestration (A2V/V2V/T2V/I2V/E2E)**. All intelligence is mediated through a **Gemma adapter layer** that calls remote ngrok endpoints (E2B/E4B) and returns structured JSON edit plans. Rendering is a separate layer that converts timelines into final media outputs (FFmpeg‑first for MVP).

Key principles:
- Timeline-based workflow for determinism and maintainability
- Decisions vs. execution separated clearly
- Gemma integration isolated behind a model client with routing, retries, and JSON validation
- Scalable module boundaries to add more intelligent behavior later without refactors

## 2. Recommended Final Module Architecture

### Core (Foundational, highest priority)
Defines the data model for everything that exists in the system.
- Element base class and child types
- Timing and transforms
- Timeline, tracks, placements
- Serialization/deserialization

### Animation (Highest priority)
Defines how elements change over time.
- Animation primitives (fade, slide, zoom, typewriter, etc.)
- Animation specs and keyframes
- Pure transformation application to timelines

### Design (Highest priority)
Defines visual styling of elements.
- Fonts, colors, strokes, shadows
- Style presets and layouts
- Aspect‑ratio aware rules

### Edit (Highest priority)
The decision module that outputs structured plans.
- Uses Gemma client (and/or rules)
- Chooses cuts, zooms, captions, overlays, music, etc.
- Outputs EditPlan (not final rendering)

### A2V (Highest priority)
Audio‑to‑Video pipeline.
- Speech alignment
- Caption timing
- Segmentation
- Calls Edit to generate plan

### V2V (Highest priority)
Video‑to‑Video pipeline.
- Reframing, cutting, caption overlays
- Calls Edit to generate plan

### T2V (Lower detail for now)
Text‑to‑Video pipeline.

### I2V (Lower detail for now)
Image‑to‑Video pipeline.

### E2E (Lower detail for now)
Orchestrates across pipelines.

### Renderer (Recommended)
Separate render module.
- Compiles Timeline to concrete output
- Initial backend: FFmpeg for MVP

### Assets (Recommended)
Media/asset registry.
- Handles asset metadata, IDs, URIs, tags
- Separate from edit decisions and design

## 3. Dependency Graph / Flow

Allowed dependencies:
```
Assets ──┐
         ├──> Core <── Design
         │       └── Animation
Gemma ───┘             │
         Edit ─────────┤
          │            │
       A2V/V2V/T2V/I2V ─┤
          │            │
        Renderer <─────┘
```

Forbidden dependencies:
- Core must not depend on Edit, Design, Animation, or Renderer.
- Design and Animation must not depend on Edit or Renderer.
- Edit must not render (only plan).
- Renderer must not call Gemma.

## 4. Project Folder Structure

```
vasp/
  core/
    elements.py
    timeline.py
    serialization.py
  animation/
    primitives.py
    engine.py
  design/
    styles.py
    presets.py
  edit/
    schemas.py
    planner.py
  a2v/
    pipeline.py
  v2v/
    pipeline.py
  gemma_client/
    schemas.py
    client.py
    router.py
  render/
    renderer.py
    ffmpeg.py
  assets/
    media.py
    registry.py
  schemas/
    base.py
  config/
    settings.py
  utils/
    retry.py
    errors.py
    logging.py
tests/
  test_imports.py
ARCHITECTURE.md
pyproject.toml
```

## 5. Core Data Models

### Element Base (Core)
```python
class Element(BaseModel):
    id: str
    type: ElementType
    timing: Timing
    transform: Transform
    design_ref: str | None
    animation_ref: str | None
```

### Child Types
- Image: source_uri
- GIF: source_uri, loop
- Caption: text, language
- Video: source_uri, trim_in, trim_out, has_audio
- Figure: figure_type, payload_uri
- Music: source_uri, loop, volume
- Sfx: source_uri, volume

### Timeline (Core)
```python
class Timeline(BaseModel):
    id: str
    tracks: list[Track]
    fps: int
    resolution: tuple[int, int]
    duration: float
```

## 6. Edit Timeline and Edit Decision Schema

### EditPlan (Edit output)
```json
{
  "id": "plan_001",
  "decisions": [
    {
      "id": "decision_1",
      "type": "caption",
      "start": 2.3,
      "duration": 3.2,
      "target_element_id": null,
      "payload": {
        "text": "Hello world",
        "style_ref": "caption_bold"
      }
    }
  ]
}
```

### Timeline Output (Compiled)
```json
{
  "id": "timeline_001",
  "fps": 30,
  "resolution": [1080, 1920],
  "duration": 12.0,
  "tracks": [
    {
      "id": "track_video",
      "type": "video",
      "items": [
        {
          "id": "item_1",
          "element_id": "video_1",
          "track_id": "track_video",
          "start": 0.0,
          "duration": 12.0,
          "layer": 0
        }
      ]
    }
  ]
}
```

## 7. Module Interfaces

### Core
Exposes element and timeline classes. Consumed by all other modules.

### Animation
Input: Timeline + AnimationSpec[]  
Output: Transformed Timeline

### Design
Input: Element or Element.id, DesignStyle or preset id  
Output: Resolved styles for rendering

### Edit
Input: Context (audio, video, text, assets, analysis)  
Output: EditPlan (structured decisions)

### A2V/V2V
Input: Audio/video + optional context  
Output: Timeline via EditPlanner + PlanCompiler

### Renderer
Input: Timeline + resolved styles + animations  
Output: Final media artifact

## 8. Render and Asset Management Recommendations

### Renderer
Why needed:
- Keeps pipeline clean by separating planning and execution
- Swappable backend for performance or quality improvements

Placement: independent module used only after timeline generation.

### Assets
Why needed:
- Centralized asset metadata
- Clean separation from edit decisions
- Enables future caching, tagging, search

## 9. Gemma Endpoint Integration Layer

### Requirements
Gemma E2B/E4B only, via ngrok. All model usage must flow through a client adapter.

### Recommended Design
- GemmaClient with generate() and generate_json()
- ModelRouter that chooses E2B or E4B
- Settings controls endpoints and timeouts via env vars
- JSON validation with repair attempts

### Request / Response Shape (example)
```json
{
  "prompt": "Return an edit plan JSON...",
  "max_tokens": 512,
  "temperature": 0.2,
  "top_p": 0.9
}
```

### Retry / Failure Strategy
- 3 attempts with exponential backoff
- On invalid JSON: attempt substring extraction
- If still invalid: raise ModelAPIError and fall back to rule-based planner

### When to Use E2B vs E4B
- E2B: simple edits, caption timing, light segmentation
- E4B: complex narrative planning, style-aware edits, dense media composition

## 10. Step-by-Step Solo Implementation Order

1. Core + Schemas
2. Design + Animation
3. Edit (Rule-Based MVP)
4. A2V/V2V pipelines
5. Renderer (FFmpeg skeleton)
6. Gemma integration
7. Assets module

Freeze early: Core + Timeline schema.  
Postpone: T2V/I2V/E2E advanced logic.

## 11. Risks and Anti-Patterns to Avoid

- Mixing edit decisions with rendering logic
- Direct model calls scattered across modules
- Storing raw model outputs without schema validation
- Core types polluted with AI-specific behavior
- Animation or Design applying edits rather than styles/motion
