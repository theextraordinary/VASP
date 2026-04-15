from __future__ import annotations

import json
from typing import Iterable


def json_validity_rate(predictions: Iterable[str]) -> float:
    preds = list(predictions)
    if not preds:
        return 0.0
    valid = 0
    for text in preds:
        try:
            json.loads(text)
            valid += 1
        except Exception:
            pass
    return valid / len(preds)
