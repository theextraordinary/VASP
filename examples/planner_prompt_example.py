from __future__ import annotations

import json
from pathlib import Path

from vasp.planner.build_planner_prompt import build_planner_prompt
from vasp.planner.current_video_state import build_current_video_state


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    element_path = root / "output" / "element2_compact.txt"
    schema_path = root / "vasp" / "schemas" / "element_capability_schema.json"
    out_prompt_path = root / "output" / "planner_input_prompt_logic_v2.txt"

    elements = json.loads(element_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    video = elements.get("video", {}) if isinstance(elements, dict) else {}
    size = video.get("size", {}) if isinstance(video, dict) else {}
    canvas = {
        "width": int(float(size.get("width", 1080) or 1080)),
        "height": int(float(size.get("height", 1920) or 1920)),
        "fps": int(float(video.get("fps", 30) or 30)),
    }
    duration = _compute_duration(elements)
    current_state = build_current_video_state(elements, canvas, duration)
    word_map = _extract_word_map(elements)

    prompt = build_planner_prompt(
        user_instruction=(
            "Create a compact high-retention edit logic plan with strong caption sync, "
            "safe placements, and only context-matching media usage."
        ),
        elements=elements,
        transcript_word_timing=word_map,
        canvas=canvas,
        current_video_state=current_state,
        element_capability_rules=schema,
        video_duration=duration,
    )

    out_prompt_path.write_text(prompt, encoding="utf-8")
    print(f"Saved planner prompt: {out_prompt_path}")


def _compute_duration(elements: dict) -> float:
    max_end = 0.0
    for e in elements.get("elements", []) if isinstance(elements, dict) else []:
        if not isinstance(e, dict):
            continue
        for a in e.get("actions", []) if isinstance(e.get("actions"), list) else []:
            if not isinstance(a, dict):
                continue
            try:
                max_end = max(max_end, float(a.get("t_end", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
    return round(max_end if max_end > 0 else 60.0, 3)


def _extract_word_map(elements: dict) -> list[dict]:
    for e in elements.get("elements", []) if isinstance(elements, dict) else []:
        if not isinstance(e, dict):
            continue
        props = e.get("properties", {}) if isinstance(e.get("properties"), dict) else {}
        if str(props.get("type", "")).lower() != "caption":
            continue
        meta = props.get("metadata", {}) if isinstance(props.get("metadata"), dict) else {}
        wm = meta.get("word_timing_map")
        if isinstance(wm, list):
            return [w for w in wm if isinstance(w, dict)]
    return []


if __name__ == "__main__":
    main()

