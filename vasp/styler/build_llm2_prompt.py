from __future__ import annotations

import json
from typing import Any


def build_llm2_prompt(
    user_instruction: str,
    validated_llm1_output: dict[str, Any],
    element_capability_schema: dict[str, Any],
    style_rules: dict[str, Any],
) -> str:
    return (
        "You are LLM2 Styler for a video editing pipeline.\n"
        "Your job is to add style/detail properties only.\n"
        "Do NOT change core timing or placement unless explicitly allowed by style_rules.\n"
        "Keep captions readable and style coherent.\n"
        "Use emphasis sparingly at strong moments.\n"
        "Do not add impossible properties for element classes.\n\n"
        "Return ONLY valid JSON.\n"
        "Do not include markdown.\n"
        "Do not include explanation outside JSON.\n"
        "Do not invent unknown element ids.\n"
        "Do not use forbidden class properties/behaviors.\n\n"
        f"USER_INSTRUCTION:\n{user_instruction}\n\n"
        f"VALIDATED_LLM1_OUTPUT:\n{json.dumps(validated_llm1_output, ensure_ascii=False, indent=2)}\n\n"
        f"ELEMENT_CAPABILITY_SCHEMA:\n{json.dumps(element_capability_schema, ensure_ascii=False, indent=2)}\n\n"
        f"STYLE_RULES:\n{json.dumps(style_rules, ensure_ascii=False, indent=2)}\n\n"
        "Expected output schema:\n"
        "{\n"
        "  \"styled_element_table\": [\n"
        "    {\n"
        "      \"element_id\": \"string\",\n"
        "      \"font_family\": \"string|null\",\n"
        "      \"font_size\": \"number|null\",\n"
        "      \"font_weight\": \"string|null\",\n"
        "      \"text_color\": \"string|null\",\n"
        "      \"highlight_color\": \"string|null\",\n"
        "      \"background_color\": \"string|null\",\n"
        "      \"opacity\": \"number\",\n"
        "      \"border_radius\": \"number|null\",\n"
        "      \"shadow\": \"string|null\",\n"
        "      \"animation_in\": \"string|null\",\n"
        "      \"animation_out\": \"string|null\",\n"
        "      \"animation_during\": \"string|null\",\n"
        "      \"transition\": \"string|null\",\n"
        "      \"crop\": \"object|null\",\n"
        "      \"scale\": \"number|null\",\n"
        "      \"rotation\": \"number|null\",\n"
        "      \"volume\": \"number|null\",\n"
        "      \"extra_renderer_props\": {}\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )

