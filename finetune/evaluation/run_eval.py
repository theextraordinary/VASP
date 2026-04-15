from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from finetune.evaluation.eval_json_validity import json_validity_rate
from finetune.evaluation.eval_task_metrics import basic_task_metrics, schema_validity_rate


def _assistant_from_row(row: dict[str, Any]) -> str:
    messages = row.get("messages", [])
    for message in messages:
        if message.get("role") == "assistant":
            return message.get("content", "")
    return ""


def _load_predictions(predictions_path: str, references_path: str) -> list[str]:
    pred_file = Path(predictions_path)
    if pred_file.exists():
        preds = []
        for line in pred_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            preds.append(payload.get("prediction", ""))
        return preds

    # fallback: evaluate target outputs from references as sanity baseline
    preds = []
    for line in Path(references_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        preds.append(_assistant_from_row(row))
    return preds


def main() -> None:
    parser = argparse.ArgumentParser(description="Run compact VASP fine-tune evaluation.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    preds = _load_predictions(cfg["predictions_path"], cfg["references_path"])

    report = {
        "count": len(preds),
        "json_validity_rate": json_validity_rate(preds),
        "schema_validity_rate": schema_validity_rate(preds),
    }
    report.update(basic_task_metrics(preds))

    report_path = Path(cfg["report_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"[eval] report -> {report_path}")


if __name__ == "__main__":
    main()
