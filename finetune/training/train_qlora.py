from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any

import yaml
from datasets import Dataset, DatasetDict
from transformers import Trainer, TrainingArguments

from finetune.quality.contracts import check_planner_output, check_refiner_text
from finetune.training.collator import build_collator
from finetune.training.formatting import example_to_text
from finetune.training.model_setup import load_model_and_tokenizer
from finetune.training.save_utils import ensure_output_dir


def load_cfg(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _msg(row: dict[str, Any], role: str) -> str:
    for m in row.get("messages", []):
        if m.get("role") == role:
            return str(m.get("content", ""))
    return ""


def _row_id_prefix(row: dict[str, Any]) -> str:
    rid = str(row.get("id", ""))
    if rid.startswith("planner_"):
        return "planner"
    if rid.startswith("refiner_"):
        return "refiner"
    return str(row.get("task", ""))


def _filter_rows(rows: list[dict[str, Any]], *, enable_contract_filter: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not enable_contract_filter:
        return rows, []
    kept: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for row in rows:
        kind = _row_id_prefix(row)
        assistant = _msg(row, "assistant")
        user = _msg(row, "user")
        if "planner" in kind:
            check = check_planner_output(assistant, user_prompt=user)
        elif "refiner" in kind:
            planner_text = ""
            i = user.find("PLANNER_TEXT:")
            j = user.find("ELEMENT_COMPACT:")
            if i != -1 and j != -1 and j > i:
                planner_text = user[i + len("PLANNER_TEXT:") : j].strip()
            check = check_refiner_text(assistant, planner_text=planner_text)
        else:
            # keep unknown tasks to avoid accidental data loss
            check = None
        if check is None or check.ok:
            kept.append(row)
        else:
            failed.append(
                {
                    "id": row.get("id"),
                    "task": row.get("task"),
                    "errors": check.errors,
                    "score": check.score,
                    "details": check.details,
                }
            )
    return kept, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Gemma E2B with QLoRA for VASP JSON planning.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = load_cfg(args.config)
    ensure_output_dir(cfg["output_dir"])

    model, tokenizer = load_model_and_tokenizer(cfg)

    raw_train = _load_jsonl(cfg["train_jsonl"])
    raw_val = _load_jsonl(cfg["val_jsonl"])
    kept_train, failed_train = _filter_rows(raw_train, enable_contract_filter=bool(cfg.get("enable_contract_filter", True)))
    kept_val, failed_val = _filter_rows(raw_val, enable_contract_filter=bool(cfg.get("enable_contract_filter", True)))

    if not kept_train or not kept_val:
        raise RuntimeError("Contract filtering removed all train/val rows. Disable filter or fix dataset.")

    failure_log = cfg.get("contract_failure_log")
    if failure_log:
        fp = Path(str(failure_log))
        fp.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "train_total": len(raw_train),
            "train_kept": len(kept_train),
            "val_total": len(raw_val),
            "val_kept": len(kept_val),
            "train_failed": failed_train,
            "val_failed": failed_val,
        }
        fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[train] wrote contract failure log -> {fp}")

    dataset = DatasetDict(
        {
            "train": Dataset.from_list(kept_train),
            "validation": Dataset.from_list(kept_val),
        }
    )
    print(
        f"[train] contract-filter kept train={len(kept_train)}/{len(raw_train)} "
        f"val={len(kept_val)}/{len(raw_val)}"
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

    # Transformers API compatibility:
    # some versions use `evaluation_strategy`, others `eval_strategy`.
    ta_params = inspect.signature(TrainingArguments.__init__).parameters
    strategy_key = "evaluation_strategy" if "evaluation_strategy" in ta_params else "eval_strategy"

    training_kwargs = dict(
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
    training_kwargs[strategy_key] = str(cfg["evaluation_strategy"])

    training_args = TrainingArguments(**training_kwargs)

    trainer_kwargs = dict(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        data_collator=build_collator(tokenizer),
    )
    # Transformers API compatibility:
    # older versions accept `tokenizer=...`; newer versions replaced it with
    # `processing_class=...`.
    tr_params = inspect.signature(Trainer.__init__).parameters
    if "tokenizer" in tr_params:
        trainer_kwargs["tokenizer"] = tokenizer
    elif "processing_class" in tr_params:
        trainer_kwargs["processing_class"] = tokenizer

    trainer = Trainer(**trainer_kwargs)

    trainer.train(resume_from_checkpoint=cfg.get("resume_from_checkpoint"))
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print(f"[train] saved adapter and tokenizer to {cfg['output_dir']}")


if __name__ == "__main__":
    main()
