from __future__ import annotations

from typing import Any


def format_messages_for_sft(messages: list[dict[str, str]], tokenizer: Any) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)

    # fallback simple format
    chunks = []
    for message in messages:
        role = message["role"].upper()
        chunks.append(f"{role}: {message['content']}")
    return "\n\n".join(chunks)


def example_to_text(example: dict[str, Any], tokenizer: Any) -> dict[str, str]:
    return {"text": format_messages_for_sft(example["messages"], tokenizer)}
