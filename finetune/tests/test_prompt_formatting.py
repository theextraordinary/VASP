from __future__ import annotations

from finetune.prompts.task_templates import build_messages


def test_prompt_message_roles() -> None:
    messages = build_messages(
        system_prompt="json only",
        input_payload={"task": {"type": "a2v_edit_plan"}},
        output_json='{"id":"x","task_type":"a2v_edit_plan","decisions":[]}',
    )
    assert [m["role"] for m in messages] == ["system", "user", "assistant"]
