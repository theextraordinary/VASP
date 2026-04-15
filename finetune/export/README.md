# Export Utilities

This folder provides scripts to prepare trained adapters for downstream use.

## Typical Flow

1. Train QLoRA adapter in `finetune/output/...`
2. Optionally merge adapter into base model weights
3. Export Hugging Face-compatible artifacts

## Scripts

- `merge_lora.py`: merge PEFT adapter with base model
- `export_hf.py`: save tokenizer/model in a clean HF folder

## Mobile Boundary

This pipeline prepares clean artifacts only.
Actual mobile conversion/packaging is intentionally out of scope here.
