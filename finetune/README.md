# VASP Gemma 4 E2B Fine-Tuning (Phase 1)

This folder adds a production-minded fine-tuning subsystem for VASP's decision layer.

## Problem Being Solved

Phase 1 trains Gemma 4 E2B to convert compact VASP-style structured inputs into strict JSON edit plans for A2V/Edit planning.

- Input: structured media/transcript/task JSON
- Output: strict JSON only (`a2v_edit_plan`)
- Scope: decision layer only (no rendering logic)

## Why Phase 1 Is Narrow

VASP is timeline-first and architecture-separated. We first optimize one reliable capability:

1. JSON validity
2. Schema compliance
3. Deterministic field behavior

This gives a stable base before broader tasks.

## Folder Overview

- `configs/`: training/eval/data configs
- `data/`: schemas, dataset builder, seed train/val files
- `prompts/`: system prompt and reusable prompt templates
- `training/`: QLoRA + SFT training entrypoint and utilities
- `evaluation/`: JSON/schema/task metric evaluation
- `export/`: LoRA merge and Hugging Face export scripts
- `notebooks/`: Colab Pro+ notebook
- `tests/`: dataset/prompt/json tests

## Dataset Format

Each row is chat-format JSONL:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "...input JSON..."},
    {"role": "assistant", "content": "...output JSON only..."}
  ]
}
```

## Run Locally

```bash
python -m finetune.data.make_vasp_finetune_dataset --config finetune/configs/data.yaml
python -m finetune.training.train_qlora --config finetune/configs/train_e2b_qlora.yaml
python -m finetune.evaluation.run_eval --config finetune/configs/eval.yaml
```

## Run in Colab Pro+

Use `finetune/notebooks/colab_train_e2b_qlora.ipynb` top-to-bottom.

The notebook:
- installs deps
- builds dataset
- trains adapters
- runs eval
- writes artifacts to Drive

## Artifacts Produced

- LoRA checkpoints (adapter-only)
- tokenizer snapshot
- eval report JSON
- optional merged full model (for downstream conversion path)

## Evaluate Before Mobile/On-Device

Check:
1. JSON validity rate
2. Schema validity rate
3. Unsupported-field rate
4. Timing parse success
5. Decision-type sanity

## Phase 2 Recommendations

- Expand task coverage (multi-scene, richer transitions)
- Add hard negative examples for invalid field hallucinations
- Add inference-time constrained decoding for strict JSON
- Add domain adaptation with real editor-labeled examples
