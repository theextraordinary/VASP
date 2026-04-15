from __future__ import annotations

import json
from typing import Any, Optional

from vasp.llm.client import LLMClient
from vasp.llm.schemas import LLMRequest, LLMModel
from vasp.planner.schemas import LLM1Plan


def plan_edit(
    *,
    instruction: str,
    elements_json: dict[str, Any],
    planner_prompt_override: Optional[str] = None,
    model: LLMModel = "e2b",
    client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """Planner stage: high-level composition decisions."""
    client = client or LLMClient()
    prompt = planner_prompt_override or _build_planner_prompt(instruction, elements_json)
    req = LLMRequest(model=model, prompt=prompt, temperature=0.2)
    try:
        raw = client.generate_json(req)
        validated = LLM1Plan.model_validate(raw)
    except Exception:
        validated = LLM1Plan.model_validate(_fallback_plan(instruction, elements_json))
    enhanced = _enhance_plan(instruction, elements_json, validated.model_dump())
    validated = LLM1Plan.model_validate(enhanced)
    return json.loads(validated.model_dump_json())


def _build_planner_prompt(instruction: str, elements_json: dict[str, Any]) -> str:
    compact_elements = _compact_elements(elements_json)
    return (
        "You are Planner (LLM-1), a composition planner for a video edit. "
        "Only output valid JSON that matches this schema:\n"
        "{\n"
        '  "decisions": [\n'
        "    {\n"
        '      "element_id": "string",\n'
        '      "t_start": 0.0,\n'
        '      "t_end": 1.0,\n'
        '      "purpose": "optional string",\n'
        '      "placement_zone": "optional string",\n'
        '      "animation_ref": "optional string",\n'
        '      "design_ref": "optional string",\n'
        '      "caption_text": "optional string for caption elements"\n'
        "    }\n"
        "  ],\n"
        '  "notes": "optional string"\n'
        "}\n\n"
        "Guidelines:\n"
        "- Keep decisions high-level.\n"
        "- Prefer placement_zone values from: center, top, bottom, left, right.\n"
        "- Use animation_ref examples: subtle_zoom, pop, pulse, bounce, shake, wiggle, slide_up, slide_left, fade_in.\n"
        "- Use design_ref examples: clean_caption, rounded_card, meme_caption.\n\n"
        f"USER INSTRUCTION:\n{instruction}\n\n"
        f"ELEMENTS INVENTORY (compact):\n{json.dumps(compact_elements, indent=2)}\n"
    )


def _compact_elements(elements_json: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {"version": elements_json.get("version"), "elements": []}
    for item in elements_json.get("elements", []):
        actions = item.get("actions", [])
        first = actions[0] if actions else {}
        compact["elements"].append(
            {
                "element_id": item.get("element_id"),
                "timing": item.get("timing"),
                "first_action": {
                    "op": first.get("op"),
                    "t_start": first.get("t_start"),
                    "t_end": first.get("t_end"),
                },
            }
        )
    return compact


def _fallback_plan(instruction: str, elements_json: dict[str, Any]) -> dict[str, Any]:
    _ = instruction
    decisions = []
    for item in elements_json.get("elements", []):
        timing = item.get("timing") or {"start": 0.0, "duration": 5.0}
        start = float(timing.get("start", 0.0))
        dur = float(timing.get("duration", 5.0))
        decisions.append(
            {
                "element_id": item.get("element_id"),
                "t_start": start,
                "t_end": start + dur,
                "purpose": "default_flow",
                "placement_zone": "center",
                "animation_ref": "subtle_zoom",
                "design_ref": "clean_caption",
            }
        )
    return {"decisions": decisions, "notes": "fallback planner output"}


def _enhance_plan(instruction: str, elements_json: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    decisions = list(plan.get("decisions", []))
    by_id = {d.get("element_id"): d for d in decisions if d.get("element_id")}
    dramatic = "dramatic" in instruction.lower() or "creative" in instruction.lower()

    for item in elements_json.get("elements", []):
        element_id = item.get("element_id")
        if not element_id:
            continue
        timing = item.get("timing") or {"start": 0.0, "duration": 5.0}
        start = float(timing.get("start", 0.0))
        end = start + float(timing.get("duration", 5.0))
        if element_id not in by_id:
            decisions.append(
                {
                    "element_id": element_id,
                    "t_start": start,
                    "t_end": end,
                    "purpose": "auto_insert",
                    "placement_zone": "center",
                    "animation_ref": "subtle_zoom",
                    "design_ref": "clean_caption",
                }
            )
            by_id[element_id] = decisions[-1]

        d = by_id[element_id]
        d.setdefault("t_start", start)
        d.setdefault("t_end", end)
        d.setdefault("placement_zone", "center")
        if dramatic:
            d.setdefault("animation_ref", "subtle_zoom")
            if str(element_id).startswith("caption_"):
                d.setdefault("design_ref", "meme_caption")
            else:
                d.setdefault("design_ref", "rounded_card")

    # Ensure captions are AI-themed and styled through planner intent.
    for d in decisions:
        if str(d.get("element_id", "")).startswith("caption_"):
            d.setdefault("caption_text", "AI is transforming creation.")
            d.setdefault("design_ref", "meme_caption" if dramatic else "clean_caption")
            d.setdefault("animation_ref", "pop")
            d.setdefault("placement_zone", "bottom")

    plan["decisions"] = decisions
    return plan
