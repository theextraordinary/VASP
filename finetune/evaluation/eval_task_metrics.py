from __future__ import annotations

import json
from typing import Iterable

from vasp.finetune_support.json_schemas import A2VEditPlan


def schema_validity_rate(predictions: Iterable[str]) -> float:
    preds = list(predictions)
    if not preds:
        return 0.0
    valid = 0
    for text in preds:
        try:
            A2VEditPlan.model_validate_json(text)
            valid += 1
        except Exception:
            pass
    return valid / len(preds)


def basic_task_metrics(predictions: Iterable[str]) -> dict[str, float]:
    parsed_plans = []
    for text in predictions:
        try:
            parsed_plans.append(A2VEditPlan.model_validate_json(text))
        except Exception:
            continue

    if not parsed_plans:
        return {
            "avg_decision_count": 0.0,
            "timing_parse_success_rate": 0.0,
            "unsupported_field_rate": 0.0,
        }

    decision_counts = [len(plan.decisions) for plan in parsed_plans]
    timing_total = 0
    timing_ok = 0
    unsupported = 0
    total_objects = 0

    for plan in parsed_plans:
        obj = json.loads(plan.model_dump_json())
        total_objects += 1
        allowed = {"id", "task_type", "decisions"}
        unsupported += len(set(obj.keys()) - allowed)
        for decision in plan.decisions:
            timing_total += 1
            if isinstance(decision.start, (float, int)) and isinstance(decision.duration, (float, int)):
                timing_ok += 1

    return {
        "avg_decision_count": sum(decision_counts) / len(decision_counts),
        "timing_parse_success_rate": (timing_ok / timing_total) if timing_total else 0.0,
        "unsupported_field_rate": unsupported / total_objects if total_objects else 0.0,
    }
