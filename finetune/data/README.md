# Data Notes

This folder contains dataset tooling and sample JSONL files for Phase 1 fine-tuning.

## Files

- `schemas.py`: training row and plan schema utilities
- `make_vasp_finetune_dataset.py`: bootstrap + hand-authored dataset builder
- `sample_train.jsonl` / `sample_val.jsonl`: seed examples
- `a2v_curated_seed.jsonl`: task-specific seed rows for planner/refiner tuning
- `make_a2v_supervised_pairs.py`: append supervised rows from current pipeline artifacts

## Source of Truth

The canonical plan schema lives in:

- `vasp/finetune_support/json_schemas.py`

The data builder validates output plans against that schema before writing JSONL rows.

## Add Real A2V Rows

Append new supervised rows from your latest run:

```bash
python -m finetune.data.make_a2v_supervised_pairs \
  --instruction "Create a caption-first A2V reel" \
  --append-planner --append-refiner
```

Default inputs:
- `output/element2_compact.txt`
- `output/planner.txt`
- `output/inter.json`

Default output file:
- `finetune/data/a2v_curated_seed.jsonl`
