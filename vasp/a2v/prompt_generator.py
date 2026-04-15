from __future__ import annotations

import json
from typing import Any


def a2v_prompt_generator(
    *,
    instruction: str,
    instruction_1: str | None,
    instruction_2: str | None,
    instruction_3: str | None,
    media_json: dict[str, Any],
    element_json: dict[str, Any] | None = None,
    elements_json: dict[str, Any] | None = None,
    element_props_json: dict[str, Any] | None = None,
) -> str:
    """Generate a compact planner prompt from instruction bundle + serialized artifacts."""
    if element_json is None:
        # Backward-compatible fallback for older callers/tests.
        if elements_json is not None:
            element_json = elements_json
        else:
            element_json = {"elements": []}

    transcript_summary = _collect_transcript_summary(media_json)
    compact_elements = _compact_elements(element_json)
    compact_props = _compact_props(element_json)
    instruction_bundle = [instruction]
    for value in (instruction_1, instruction_2, instruction_3):
        if value and str(value).strip():
            instruction_bundle.append(str(value).strip())

    payload = {
        "instructions": instruction_bundle,
        "transcript_summary": transcript_summary,
        "elements": compact_elements,
        "element_props": compact_props,
    }

    return (
        "You are the A2V planning helper. Build timeline decisions from structured context.\n"
        "Return strict JSON only following planner schema.\n"
        "Prioritize caption timing, emphasis alignment, and clear visual pacing.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _collect_transcript_summary(media_json: dict[str, Any]) -> dict[str, Any]:
    ctx = media_json.get("media_context", {})
    analysis = ctx.get("analysis", {}) if isinstance(ctx, dict) else {}
    transcripts: list[dict[str, Any]] = []
    for media_id, block in analysis.items():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        words = transcript.get("words", [])
        stats = transcript.get("word_stats", {})
        transcripts.append(
            {
                "media_id": media_id,
                "language": transcript.get("language"),
                "full_text": transcript.get("full_text", "")[:2000],
                "word_count": len(words) if isinstance(words, list) else 0,
                "important_count": (stats or {}).get("important_count", 0),
                "avg_pause_s": (stats or {}).get("avg_pause_s", 0.0),
            }
        )
    return {"tracks": transcripts}


def _compact_elements(element_json: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in element_json.get("elements", []):
        out.append(
            {
                "element_id": e.get("element_id"),
                "timing": e.get("timing"),
                "action_count": len(e.get("actions", [])),
                "type": (e.get("properties", {}) or {}).get("type"),
            }
        )
    return out


def _compact_props(element_json: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in element_json.get("elements", []):
        p = e.get("properties", {})
        transform = p.get("transform", {}) if isinstance(p, dict) else {}
        out.append(
            {
                "element_id": e.get("element_id"),
                "type": p.get("type") if isinstance(p, dict) else None,
                "timing": p.get("timing") if isinstance(p, dict) else None,
                "x": transform.get("x") if isinstance(transform, dict) else None,
                "y": transform.get("y") if isinstance(transform, dict) else None,
            }
        )
    return out
