from __future__ import annotations

import json
from typing import Any

from vasp.finetune_support.json_schemas import A2VEditPlan


def normalize_input_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Keep inputs compact and deterministic for training.
    """
    timeline = payload.get("timeline", {})
    transcript = payload.get("transcript", {})
    media = payload.get("media", [])
    task = payload.get("task", {"type": "a2v_edit_plan"})
    return {
        "task": task,
        "timeline": {
            "duration_s": float(timeline.get("duration_s", 0.0)),
            "fps": int(timeline.get("fps", 30)),
        },
        "media": media,
        "transcript": transcript,
    }


def build_chat_row(system_prompt: str, input_payload: dict[str, Any], output_plan: A2VEditPlan) -> dict[str, Any]:
    user_content = json.dumps(input_payload, ensure_ascii=False, separators=(",", ":"))
    assistant_content = output_plan.model_dump_json(exclude_none=True)
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }
