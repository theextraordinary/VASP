from __future__ import annotations

import json
from typing import Any


def build_llm1_prompt(
    user_instruction: str,
    elements: dict[str, Any],
    element_capability_schema: dict[str, Any],
    current_video_state: dict[str, Any],
    output_schema: dict[str, Any],
) -> str:
    """Build a strict JSON-only planning prompt for LLM1."""
    elements_text = json.dumps(elements, ensure_ascii=False, indent=2)
    cap_text = json.dumps(element_capability_schema, ensure_ascii=False, indent=2)
    state_text = json.dumps(current_video_state, ensure_ascii=False, indent=2)
    out_schema_text = json.dumps(output_schema, ensure_ascii=False, indent=2)
    input_block = _build_human_input_block(elements)

    return (
        "You are a professional video edit planner.\n"
        "Understand every element class using the provided element capability schema.\n"
        "Never assign impossible behaviors to an element.\n"
        "Use current_video_state to avoid conflicts with existing timeline occupancy.\n"
        "Caption grouping is YOUR job: input caption words are ungrouped timing atoms.\n"
        "Do not reuse any pre-grouped caption chunks from input actions.\n"
        "Build fresh caption groups from word timing map deterministically.\n"
        "Keep placements inside canvas bounds.\n"
        "Avoid bad overlaps and keep captions synced with audio/transcript timing.\n"
        "Visuals must support spoken topic/context and appear when related words/topics are spoken.\n"
        "Avoid black gaps in expected timeline coverage.\n"
        "Maintain clean, readable, high-retention editing choices.\n\n"
        "Return ONLY valid JSON.\n"
        "Do not include markdown.\n"
        "Do not include explanation outside JSON.\n"
        "Do not invent unknown element ids unless action is \"add\" and is_new_element is true.\n"
        "Do not use properties forbidden by the element capability schema.\n\n"
        "USER_INSTRUCTION:\n"
        f"{user_instruction}\n\n"
        "ELEMENT_CAPABILITY_SCHEMA:\n"
        f"{cap_text}\n\n"
        "CURRENT_VIDEO_STATE:\n"
        f"{state_text}\n\n"
        "INPUT_ELEMENTS:\n"
        f"{elements_text}\n\n"
        "## Input\n\n"
        f"{input_block}\n\n"
        "OUTPUT_SCHEMA (must follow exactly):\n"
        f"{out_schema_text}\n"
    )


def _build_human_input_block(elements: dict[str, Any]) -> str:
    transcript = ""
    word_map: list[dict[str, Any]] = []
    image_data: list[dict[str, Any]] = []
    audio_data: list[dict[str, Any]] = []

    for e in elements.get("elements", []) if isinstance(elements, dict) else []:
        if not isinstance(e, dict):
            continue
        etype = str(e.get("type", "")).lower()
        eid = str(e.get("element_id", "")).strip()
        props = e.get("properties", {}) if isinstance(e.get("properties"), dict) else {}
        timing = e.get("timing", {}) if isinstance(e.get("timing"), dict) else {}
        meta = props.get("metadata", {}) if isinstance(props.get("metadata"), dict) else {}

        start = _num(timing.get("start"), 0.0)
        duration = _num(timing.get("duration"), 0.0)
        end = max(start, start + duration)
        timing_s = f"{start:.3f}-{end:.3f}"

        if etype == "caption":
            transcript = str(props.get("text") or meta.get("transcript") or transcript)
            wm = props.get("word_timing_map")
            if not isinstance(wm, list):
                wm = meta.get("word_timing_map")
            if isinstance(wm, list) and wm:
                word_map = wm
        elif etype in {"image", "video", "gif"}:
            image_data.append(
                {
                    "id": eid or None,
                    "path": props.get("source_uri"),
                    "timing": timing_s,
                    "about": meta.get("about"),
                    "aim": meta.get("aim"),
                }
            )
        elif etype in {"music", "audio", "sfx"}:
            audio_data.append(
                {
                    "id": eid or None,
                    "path": props.get("source_uri"),
                    "timing": timing_s,
                }
            )

    transcript = transcript.strip() if transcript else ""
    block = [
        "### Transcript",
        f"\"{transcript}\"" if transcript else "\"\"",
        "",
        "### Caption Word Timing Map",
        json.dumps(word_map, ensure_ascii=False),
        "",
        "### Image Data",
        json.dumps(image_data, ensure_ascii=False),
        "",
        "### Audio Data",
        json.dumps(audio_data, ensure_ascii=False),
        "",
        "### Allowed Animations",
        "[fade in/out, jump in/out, roll in/out]",
    ]
    return "\n".join(block)


def _num(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default
