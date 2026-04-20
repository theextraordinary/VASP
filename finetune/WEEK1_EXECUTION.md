# Week-1 Deep Tuning Runbook

## 1) Build curriculum datasets (Stage A/B/C)
```bash
python -m finetune.data.build_curriculum_datasets \
  --planner finetune/data/planner_train_paired.jsonl \
  --refiner finetune/data/refiner_train_paired.jsonl \
  --out-dir finetune/data/curriculum \
  --val-ratio 0.05
```

## 2) Validate paired contracts before training
```bash
python -m finetune.quality.validate_paired_dataset \
  --planner finetune/data/planner_train_paired.jsonl \
  --refiner finetune/data/refiner_train_paired.jsonl \
  --out output/quality/paired_validation_report.json
```

## 3) Train SFT curriculum
Stage A (planner deterministic format)
```bash
python -m finetune.training.train_qlora --config finetune/configs/train_stage_a_planner_qlora.yaml
```

Stage B (refiner schema fidelity)
```bash
python -m finetune.training.train_qlora --config finetune/configs/train_stage_b_refiner_qlora.yaml
```

Stage C (end-to-end refiner robustness)
```bash
python -m finetune.training.train_qlora --config finetune/configs/train_stage_c_e2e_refiner_qlora.yaml
```

## 4) Mine hard-negatives from endpoint eval logs
```bash
python -m finetune.data.build_hard_negatives_from_endpoint_eval \
  --endpoint-eval-dir output/endpoint_eval \
  --planner finetune/data/planner_train_paired.jsonl \
  --refiner finetune/data/refiner_train_paired.jsonl \
  --out-dir finetune/data/hardneg \
  --val-ratio 0.1
```

Optional: merge hard-negatives into SFT train sets
```bash
python -m finetune.data.merge_hardneg_into_sft
```

## 5) Preference alignment (DPO)
Planner DPO:
```bash
python -m finetune.training.train_dpo --config finetune/configs/train_stage_d_planner_dpo.yaml
```

Refiner DPO:
```bash
python -m finetune.training.train_dpo --config finetune/configs/train_stage_d_refiner_dpo.yaml
```

## 6) Endpoint evaluation with per-rule failures
```bash
python scripts/eval_planner_refiner_endpoints.py \
  --planner-url "$PLANNER_URL" \
  --refiner-url "$REFINER_URL" \
  --planner-jsonl finetune/data/planner_train_paired.jsonl \
  --refiner-jsonl finetune/data/refiner_train_paired.jsonl \
  --n-independent 5 \
  --n-e2e 5 \
  --out-dir output/endpoint_eval
```

## 7) Inference-time guardrails
When running `python -m vasp.a2v.main ...`:
- planner gets deterministic repair if contract fails
- refiner gets JSON/schema repair and one contract-driven retry
- quality logs are written to:
  - `output/quality/planner_inference_score.json`
  - `output/quality/refiner_inference_score.json`
