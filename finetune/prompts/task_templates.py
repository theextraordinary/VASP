from __future__ import annotations

import json
from typing import Any


def build_user_payload(input_payload: dict[str, Any]) -> str:
    return json.dumps(input_payload, ensure_ascii=False, separators=(",", ":"))


def build_messages(system_prompt: str, input_payload: dict[str, Any], output_json: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_user_payload(input_payload)},
        {"role": "assistant", "content": output_json},
    ]
