# Colab Fine-Tuning Guide (Planner + Refiner)

## 1) Runtime
- Use `GPU` runtime in Colab (`T4` minimum; `A100` preferred).

## 2) Setup
```bash
!git clone https://github.com/<your-user>/<your-repo>.git
%cd <your-repo>
!pip -q install transformers datasets peft accelerate bitsandbytes trl pyyaml
```

## 3) Hugging Face auth (for base model download)
```python
from huggingface_hub import login
login()  # paste your HF token with access to google/gemma-4-e2b-it
```

## 4) Train Planner
```bash
!python -m finetune.training.train_qlora --config finetune/configs/train_planner_paired_qlora.yaml
```

## 5) Train Refiner
```bash
!python -m finetune.training.train_qlora --config finetune/configs/train_refiner_paired_qlora.yaml
```

## 6) Save weights to local machine
```python
!zip -r planner_e2b_qlora.zip finetune/output/planner_e2b_qlora
!zip -r refiner_e2b_qlora.zip finetune/output/refiner_e2b_qlora

from google.colab import files
files.download("planner_e2b_qlora.zip")
files.download("refiner_e2b_qlora.zip")
```

## Notes
- Final paired datasets used:
  - `finetune/data/planner_train_paired.jsonl` (420)
  - `finetune/data/refiner_train_paired.jsonl` (420)
- Train/val splits already prepared:
  - `finetune/data/planner_paired_train.jsonl` (399), `finetune/data/planner_paired_val.jsonl` (21)
  - `finetune/data/refiner_paired_train.jsonl` (399), `finetune/data/refiner_paired_val.jsonl` (21)
