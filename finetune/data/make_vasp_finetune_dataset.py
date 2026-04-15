from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import yaml

from finetune.data.schemas import TrainingRow
from vasp.finetune_support.json_schemas import A2VEditPlan, TrainingExample
from vasp.finetune_support.synthetic_examples import build_bootstrap_examples
from vasp.finetune_support.task_builders import build_chat_row, normalize_input_payload


def load_system_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def load_hand_authored(path: str | None) -> list[TrainingExample]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Hand-authored dataset not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    out: list[TrainingExample] = []
    for row in data:
        plan = A2VEditPlan.model_validate(row["output_plan"])
        out.append(TrainingExample(input_payload=row["input_payload"], output_plan=plan, tags=row.get("tags", [])))
    return out


def deduplicate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(row)
    return unique


def split_rows(rows: list[dict[str, Any]], ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    random.seed(seed)
    shuffled = rows[:]
    random.shuffle(shuffled)
    pivot = int(len(shuffled) * ratio)
    return shuffled[:pivot], shuffled[pivot:]


def write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_rows(examples: list[TrainingExample], system_prompt: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for example in examples:
        normalized_input = normalize_input_payload(example.input_payload)
        row = build_chat_row(system_prompt=system_prompt, input_payload=normalized_input, output_plan=example.output_plan)
        TrainingRow.model_validate(row)
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build VASP fine-tune dataset JSONL.")
    parser.add_argument("--config", required=True, help="Path to data.yaml")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    system_prompt = load_system_prompt(config["system_prompt_path"])

    examples: list[TrainingExample] = []
    if config.get("use_bootstrap_examples", True):
        examples.extend(build_bootstrap_examples())
    examples.extend(load_hand_authored(config.get("hand_authored_path")))

    rows = build_rows(examples, system_prompt=system_prompt)
    if config.get("deduplicate", True):
        rows = deduplicate_rows(rows)

    train_rows, val_rows = split_rows(
        rows=rows,
        ratio=float(config.get("train_split_ratio", 0.9)),
        seed=int(config.get("seed", 42)),
    )

    write_jsonl(config["train_file"], train_rows)
    write_jsonl(config["val_file"], val_rows)
    print(f"[dataset] total={len(rows)} train={len(train_rows)} val={len(val_rows)}")
    print(f"[dataset] wrote {config['train_file']}")
    print(f"[dataset] wrote {config['val_file']}")


if __name__ == "__main__":
    main()
