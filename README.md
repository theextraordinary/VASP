# VASP

VASP is a modular, timeline‑first AI video editing framework focused on clean architecture, strong foundations, and future‑ready intelligent editing workflows.

## Highlights
- Core data model for elements, timelines, and transforms
- Animation, Design, and Edit modules separated by responsibility
- Audio‑to‑Video and Video‑to‑Video pipelines
- Gemma‑only inference adapter layer
- Testable rendering utilities with JSON‑driven inputs

## Repo Structure (High‑Level)
- `vasp/` — core library and modules
- `tests/` — fixtures and render tests
- `assets/` — test media inputs
- `output/` — generated videos
- `ARCHITECTURE.md` — full architecture doc

## Quick Start
1. Place test media in `assets/inputs/` (see `assets/README.md`)
2. Run a render test:

```powershell
python tests/test_render_elements.py --only combine
```

Outputs will appear in `output/`.

## Documentation
- `ARCHITECTURE.md` — module boundaries, data models, and workflow design
- `vasp/core/README.md` — core schema + serialization guidelines

## License (ANIGMA Incorporation)
All rights reserved © 2026 ANIGMA Incorporation.

Use of this repository and its contents is restricted and governed by ANIGMA Incorporation.
