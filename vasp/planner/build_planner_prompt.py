from __future__ import annotations

import json
from typing import Any


PLANNER_OUTPUT_SCHEMA: dict[str, Any] = {
    "video_understanding": {
        "summary": "short summary of what the edit is about",
        "mood": "emotional | energetic | funny | cinematic | informative | other",
        "main_audio": "element_id",
        "main_caption": "element_id",
    },
    "asset_understanding": [
        {
            "element_id": "string",
            "type": "audio | caption | image | video | gif | sfx | music",
            "represents": "what this element contains",
            "best_use": "how it should be used in this edit",
            "usefulness": "high | medium | low",
            "reason": "why",
        }
    ],
    "timeline_plan": [
        {
            "segment_id": "string",
            "t_start": 0.0,
            "t_end": 1.0,
            "spoken_text": "string",
            "main_visual": "element_id or null",
            "supporting_elements": ["element_id"],
            "caption_behavior": "string",
            "placement": {
                "zone": "full_screen | center | top | bottom | left | right | background | none",
                "safe_for_captions": True,
            },
            "transition_in": "cut | fade | zoom | slide | pop | none",
            "transition_out": "cut | fade | zoom | slide | pop | none",
            "reason": "why this edit is good here",
        }
    ],
    "element_actions": [
        {
            "element_id": "string",
            "action": "play | show | hide | place | emphasize | transition | skip",
            "t_start": 0.0,
            "t_end": 1.0,
            "role": "main_audio | caption | background | foreground | accent | unused",
            "placement_zone": "full_screen | center | top | bottom | left | right | background | none",
            "avoid_covering": ["caption_track_1"],
            "notes_for_styler": "string",
        }
    ],
    "needs_user_input": [
        {
            "question": "string",
            "reason": "string",
            "optional": True,
        }
    ],
    "creative_suggestions": ["string"],
}


def build_planner_prompt(
    *,
    user_instruction: str,
    elements: dict[str, Any],
    transcript_word_timing: list[dict[str, Any]] | None,
    canvas: dict[str, Any],
    current_video_state: dict[str, Any],
    element_capability_rules: dict[str, Any],
    video_duration: float,
) -> str:
    """Build planner prompt for logic-only edit planning (no renderer JSON)."""
    transcript_text = _extract_transcript_text(elements)
    word_map = transcript_word_timing or _extract_word_timing(elements)
    normalized_elements = _compact_elements_for_planner(elements)

    return (
        "You are a professional short-form video editor.\n"
        "Your job is to create an edit plan, not copy the input JSON.\n"
        "Use the transcript timing as the main timeline.\n"
        "Use each media element only when its about/aim matches the spoken topic, emotion, or segment.\n"
        "Do not show all images for the full video.\n"
        "Do not stack unrelated images together.\n"
        "Do not cover captions.\n"
        "Keep captions synced to word_timing_map.\n"
        "Use the current_video_state to know what is already visible/audible.\n"
        "Place elements inside canvas bounds.\n"
        "Prefer full-screen background visuals only when they are the main visual for that segment.\n"
        "Use transitions between visual changes.\n"
        "If the provided media does not match the transcript, say so in needs_user_input or creative_suggestions.\n"
        "Do not return original elements.\n"
        "Do not include source_uri unless needed.\n"
        "Do not rewrite full caption text.\n"
        "Do not create transform/style/color values here.\n"
        "Do not output renderer JSON.\n"
        "This planner only decides editing logic.\n"
        "LLM2/styler will later add exact x/y/width/height/color/font/animation details.\n"
        "Renderer JSON will be created later by json_creator.\n"
        "Return ONLY valid JSON matching the schema.\n"
        "Do not include markdown or prose outside JSON.\n\n"
        f"USER_INSTRUCTION:\n{user_instruction}\n\n"
        f"CANVAS:\n{json.dumps(canvas, ensure_ascii=False, indent=2)}\n\n"
        f"VIDEO_DURATION_SECONDS:\n{video_duration}\n\n"
        f"ELEMENT_CAPABILITY_RULES:\n{json.dumps(element_capability_rules, ensure_ascii=False, indent=2)}\n\n"
        f"CURRENT_VIDEO_STATE:\n{json.dumps(current_video_state, ensure_ascii=False, indent=2)}\n\n"
        f"ELEMENTS_COMPACT:\n{json.dumps(normalized_elements, ensure_ascii=False, indent=2)}\n\n"
        f"TRANSCRIPT:\n{json.dumps(transcript_text, ensure_ascii=False)}\n\n"
        f"WORD_TIMING_MAP:\n{json.dumps(word_map, ensure_ascii=False, indent=2)}\n\n"
        f"OUTPUT_SCHEMA:\n{json.dumps(PLANNER_OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}\n"
    )


def _compact_elements_for_planner(elements: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"elements": []}
    for item in elements.get("elements", []) if isinstance(elements, dict) else []:
        if not isinstance(item, dict):
            continue
        props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
        meta = props.get("metadata", {}) if isinstance(props.get("metadata"), dict) else {}
        actions = item.get("actions", []) if isinstance(item.get("actions"), list) else []
        start = None
        end = None
        for act in actions:
            if not isinstance(act, dict):
                continue
            ts = _f(act.get("t_start"))
            te = _f(act.get("t_end"))
            if ts is not None:
                start = ts if start is None else min(start, ts)
            if te is not None:
                end = te if end is None else max(end, te)
        out["elements"].append(
            {
                "element_id": item.get("element_id"),
                "type": props.get("type", item.get("type")),
                "t_start": start,
                "t_end": end,
                "about": meta.get("about"),
                "aim": meta.get("aim"),
                "timing": props.get("timing"),
            }
        )
    return out


def _extract_transcript_text(elements: dict[str, Any]) -> str:
    for item in elements.get("elements", []) if isinstance(elements, dict) else []:
        if not isinstance(item, dict):
            continue
        props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
        if str(props.get("type", "")).lower() != "caption":
            continue
        text = props.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _extract_word_timing(elements: dict[str, Any]) -> list[dict[str, Any]]:
    for item in elements.get("elements", []) if isinstance(elements, dict) else []:
        if not isinstance(item, dict):
            continue
        props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
        if str(props.get("type", "")).lower() != "caption":
            continue
        meta = props.get("metadata", {}) if isinstance(props.get("metadata"), dict) else {}
        wm = meta.get("word_timing_map")
        if isinstance(wm, list):
            return [w for w in wm if isinstance(w, dict)]
    return []


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None

