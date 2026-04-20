# Refiner V3 Preset Fine-Tuning Examples

This folder contains synthetic examples for teaching Refiner V3 to choose professional preset names instead of inventing raw visual styles.

The renderer and combiner resolve preset names into deterministic layouts, caption styles, backgrounds, animations, and transitions.

The dataset teaches:
- caption-only segments should have `visual_timeline: []`
- images should use centered contained cards or safe media zones
- videos and GIFs should use clean contained visual zones
- captions should be readable, high contrast, and inside the canvas
- preset bundles should match the segment mood
- raw style objects are optional compatibility overrides, not the primary design language

Generate:

```bash
python -m vasp.a2v.finetuning.refiner_v3_presets.create_refiner_preset_examples
```

Validate:

```bash
python -m vasp.a2v.finetuning.refiner_v3_presets.validate_refiner_preset_examples
```

Outputs:
- `refiner_v3_preset_150.jsonl`
- `refiner_v3_preset_pretty.json`
- `validation_report.json`
