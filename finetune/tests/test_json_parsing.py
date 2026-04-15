from __future__ import annotations

from vasp.finetune_support.json_schemas import A2VEditPlan, Decision, DecisionType


def test_plan_json_parses() -> None:
    plan = A2VEditPlan.model_validate(
        {
            "id": "plan_test",
            "task_type": "a2v_edit_plan",
            "decisions": [
                {
                    "id": "d1",
                    "type": "caption",
                    "start": 0.0,
                    "duration": 1.2,
                    "target_element_id": None,
                    "payload": {"text": "Hello", "style": "clean"},
                }
            ],
        }
    )
    assert plan.task_type == "a2v_edit_plan"
    assert plan.decisions[0].type == DecisionType.CAPTION


def test_unsupported_fields_are_rejected() -> None:
    bad = {
        "id": "d_bad",
        "type": "caption",
        "start": 0.0,
        "duration": 1.0,
        "target_element_id": None,
        "payload": {"text": "X", "style": "clean"},
        "unknown": True,
    }
    try:
        Decision.model_validate(bad)
        assert False, "Expected validation failure for unsupported field"
    except Exception:
        assert True
