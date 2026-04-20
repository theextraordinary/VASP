from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any

import yaml
from datasets import Dataset, DatasetDict
from transformers import AutoTokenizer, TrainingArguments

from peft import PeftModel
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from trl import DPOTrainer

from finetune.training.save_utils import ensure_output_dir


def load_cfg(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _dtype(name: str):
    import torch

    name = name.lower()
    if name in {"bf16", "bfloat16"}:
        return torch.bfloat16
    if name in {"fp16", "float16"}:
        return torch.float16
    return torch.float32


def _load_model_with_adapter(cfg: dict[str, Any]):
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"], use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant = None
    if bool(cfg.get("use_4bit", True)):
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=str(cfg.get("bnb_4bit_quant_type", "nf4")),
            bnb_4bit_use_double_quant=bool(cfg.get("bnb_4bit_use_double_quant", True)),
            bnb_4bit_compute_dtype=_dtype(str(cfg.get("bnb_4bit_compute_dtype", "bfloat16"))),
        )
    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model"],
        quantization_config=quant,
        dtype=_dtype(str(cfg.get("dtype", "bfloat16"))),
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(model, cfg["sft_adapter_path"])
    return model, tokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="DPO fine-tuning on planner/refiner preference pairs.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = load_cfg(args.config)
    ensure_output_dir(cfg["output_dir"])

    model, tokenizer = _load_model_with_adapter(cfg)

    train_rows = _load_jsonl(cfg["train_jsonl"])
    val_rows = _load_jsonl(cfg["val_jsonl"])

    def normalize(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for r in rows:
            prompt = str(r.get("prompt", ""))
            chosen = str(r.get("chosen", ""))
            rejected = str(r.get("rejected", ""))
            if prompt and chosen and rejected:
                out.append({"prompt": prompt, "chosen": chosen, "rejected": rejected})
        return out

    dataset = DatasetDict(
        {
            "train": Dataset.from_list(normalize(train_rows)),
            "validation": Dataset.from_list(normalize(val_rows)),
        }
    )

    ta_params = inspect.signature(TrainingArguments.__init__).parameters
    strategy_key = "evaluation_strategy" if "evaluation_strategy" in ta_params else "eval_strategy"

    kwargs = dict(
        output_dir=cfg["output_dir"],
        learning_rate=float(cfg.get("learning_rate", 5e-6)),
        per_device_train_batch_size=int(cfg.get("per_device_train_batch_size", 1)),
        per_device_eval_batch_size=int(cfg.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(cfg.get("gradient_accumulation_steps", 16)),
        num_train_epochs=float(cfg.get("num_train_epochs", 1)),
        logging_steps=int(cfg.get("logging_steps", 10)),
        eval_steps=int(cfg.get("eval_steps", 50)),
        save_steps=int(cfg.get("save_steps", 50)),
        save_total_limit=int(cfg.get("save_total_limit", 2)),
        save_strategy=str(cfg.get("save_strategy", "steps")),
        bf16=bool(cfg.get("bf16", True)),
        fp16=bool(cfg.get("fp16", False)),
        report_to=["none"],
    )
    kwargs[strategy_key] = str(cfg.get("evaluation_strategy", "steps"))
    training_args = TrainingArguments(**kwargs)

    trainer = DPOTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        processing_class=tokenizer,
        beta=float(cfg.get("beta", 0.1)),
        max_length=int(cfg.get("max_length", 2048)),
        max_prompt_length=int(cfg.get("max_prompt_length", 1536)),
    )
    trainer.train()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print(f"[dpo] saved adapter -> {cfg['output_dir']}")


if __name__ == "__main__":
    main()

