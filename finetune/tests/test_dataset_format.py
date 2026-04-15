from __future__ import annotations

import json
from pathlib import Path

from finetune.data.schemas import TrainingRow


def test_sample_train_rows_are_valid() -> None:
    path = Path("finetune/data/sample_train.jsonl")
    assert path.exists()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        TrainingRow.model_validate(row)
