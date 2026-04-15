from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from datasets import load_dataset
from transformers import Trainer, TrainingArguments

from finetune.training.collator import build_collator
from finetune.training.formatting import example_to_text
from finetune.training.model_setup import load_model_and_tokenizer
from finetune.training.save_utils import ensure_output_dir


def load_cfg(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Gemma E2B with QLoRA for VASP JSON planning.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = load_cfg(args.config)
    ensure_output_dir(cfg["output_dir"])

    model, tokenizer = load_model_and_tokenizer(cfg)

    dataset = load_dataset(
        "json",
        data_files={"train": cfg["train_jsonl"], "validation": cfg["val_jsonl"]},
    )
    dataset = dataset.map(lambda ex: example_to_text(ex, tokenizer))

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            max_length=int(cfg.get("max_seq_length", 1024)),
            truncation=True,
            padding=False,
        )

    tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset["train"].column_names)

    training_args = TrainingArguments(
        output_dir=cfg["output_dir"],
        learning_rate=float(cfg["learning_rate"]),
        num_train_epochs=float(cfg["num_train_epochs"]),
        per_device_train_batch_size=int(cfg["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(cfg["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(cfg["gradient_accumulation_steps"]),
        warmup_ratio=float(cfg["warmup_ratio"]),
        weight_decay=float(cfg["weight_decay"]),
        logging_steps=int(cfg["logging_steps"]),
        eval_steps=int(cfg["eval_steps"]),
        save_steps=int(cfg["save_steps"]),
        save_total_limit=int(cfg["save_total_limit"]),
        evaluation_strategy=str(cfg["evaluation_strategy"]),
        save_strategy=str(cfg["save_strategy"]),
        load_best_model_at_end=bool(cfg["load_best_model_at_end"]),
        metric_for_best_model=str(cfg["metric_for_best_model"]),
        greater_is_better=bool(cfg["greater_is_better"]),
        bf16=bool(cfg.get("use_bf16", True)),
        fp16=bool(cfg.get("use_fp16", False)),
        gradient_checkpointing=bool(cfg.get("gradient_checkpointing", True)),
        seed=int(cfg.get("seed", 42)),
        report_to=["none"],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        tokenizer=tokenizer,
        data_collator=build_collator(tokenizer),
    )

    trainer.train(resume_from_checkpoint=cfg.get("resume_from_checkpoint"))
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print(f"[train] saved adapter and tokenizer to {cfg['output_dir']}")


if __name__ == "__main__":
    main()
