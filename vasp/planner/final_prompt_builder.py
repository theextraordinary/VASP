from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_caption_groups(
    word_timing_map: list[dict[str, Any]],
    *,
    pause_threshold: float = 0.35,
    max_words: int = 5,
    max_group_span_s: float = 2.0,
) -> list[dict[str, Any]]:
    """Create deterministic caption groups from word timings.

    Rules:
    - split on punctuation (.!?)
    - split when next token starts with uppercase
    - split on pause >= threshold
    - split when group has max_words
    - split when group span would exceed max_group_span_s
    """
    if not word_timing_map:
        return []

    def _ends_sentence(tok: str) -> bool:
        t = (tok or "").strip()
        return t.endswith(".") or t.endswith("!") or t.endswith("?")

    def _starts_upper(tok: str) -> bool:
        t = (tok or "").strip()
        return bool(t) and t[0].isalpha() and t[0].isupper()

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    group_start = 0.0

    for i, w in enumerate(word_timing_map):
        if not current:
            group_start = float(w["start"])
        current.append(w)

        if i == len(word_timing_map) - 1:
            groups.append(current)
            break

        nxt = word_timing_map[i + 1]
        gap = float(nxt["start"]) - float(w["end"])
        next_span = float(nxt["start"]) - group_start

        split = False
        if _ends_sentence(str(w.get("text", ""))):
            split = True
        if _starts_upper(str(nxt.get("text", ""))):
            split = True
        if gap >= pause_threshold:
            split = True
        if len(current) >= max_words:
            split = True
        if next_span > max_group_span_s:
            split = True

        if split:
            groups.append(current)
            current = []

    out: list[dict[str, Any]] = []
    for i, g in enumerate(groups):
        start = float(g[0]["start"])
        end = float(groups[i + 1][0]["start"]) if i < len(groups) - 1 else float(g[-1]["end"])
        out.append(
            {
                "group_id": f"group_{i+1}",
                "words": " ".join(str(x.get("text", "")).strip() for x in g).strip(),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
            }
        )
    return out


def build_planner_prompt_with_schema(
    *,
    element_schema: dict[str, Any],
    current_video_state: dict[str, Any],
    transcript: str,
    word_timing_map: list[dict[str, Any]],
    image_data: list[dict[str, Any]],
    audio_data: list[dict[str, Any]],
    allowed_animations: list[str],
    pause_threshold: float = 0.35,
) -> str:
    """Build one planner input prompt with system+user sections."""
    grouped = build_caption_groups(word_timing_map, pause_threshold=pause_threshold)
    groups_text = "\n".join(
        f"{g['group_id']} | {g['words']} | {g['start']:.3f} | {g['end']:.3f} | {g['duration']:.3f}"
        for g in grouped
    )

    system_content = (
        "You are a professional short-form video editor and planning model.\n\n"
        "You must follow:\n"
        "1) Element capability schema (truth source for what each class can/cannot do).\n"
        "2) Current video state (what is already visible/occupied over time).\n"
        "3) Input data exactly as provided.\n\n"
        "ELEMENT CAPABILITY SCHEMA:\n"
        f"{json.dumps(element_schema, ensure_ascii=False, indent=2)}\n\n"
        "CURRENT VIDEO STATE:\n"
        f"{json.dumps(current_video_state, ensure_ascii=False, indent=2)}\n\n"
        "Hard rules:\n"
        "- Do not alter any provided input data.\n"
        "- Do not invent new timestamps.\n"
        "- Keep strict sync.\n"
        "- Respect element capabilities.\n"
        "- Keep style clean and consistent.\n"
    )

    user_content = (
        "## Core Constraints\n"
        "- 9:16 vertical, mp4 target.\n"
        "- Keep all elements inside screen.\n"
        "- Keep style clean and consistent.\n\n"
        "## Absolute Sync Rules (Must Follow)\n"
        "1. Do not alter source word mapping.\n"
        "2. Every source word appears exactly once.\n"
        "3. Keep exact order.\n"
        "4. group_start = first word start.\n"
        "5. group_end = next group start (last group ends at last word end).\n"
        "6. No gaps and no overlaps between groups.\n"
        "7. Never invent timestamps.\n\n"
        "## Grouping Algorithm (Deterministic)\n"
        "- New group on punctuation (.!?).\n"
        "- New group when next token starts uppercase.\n"
        f"- New group when pause gap >= {pause_threshold:.2f}s.\n"
        "- Max 5 words/group.\n"
        "- Prefer 2-4 words/group where possible.\n"
        "- Keep groups in ~1-2 seconds where possible.\n\n"
        "## Caption Readability\n"
        "- Max 2 lines.\n"
        "- Safe zone y=1450..1780.\n"
        "- No overlap unless intentional layering.\n\n"
        "## Input\n\n"
        "### Transcript\n"
        f"\"{transcript}\"\n\n"
        "### Caption Word Timing Map\n"
        f"{json.dumps(word_timing_map, ensure_ascii=False)}\n\n"
        "### Caption Groups (Precomputed from timing function)\n"
        f"{groups_text}\n\n"
        "### Image Data\n"
        f"{json.dumps(image_data, ensure_ascii=False)}\n\n"
        "### Audio Data\n"
        f"{json.dumps(audio_data, ensure_ascii=False)}\n\n"
        "### Allowed Animations\n"
        f"[{', '.join(allowed_animations)}]\n\n"
        "## Output Format (Strict)\n"
        "Return plain text only:\n"
        "- Global Style\n"
        "- Caption Strategy\n"
        "- Image Strategy\n"
        "- Sync Strategy\n"
        "- Transition Policy\n\n"
        "Then return a table with:\n"
        "id | type | position | size | start | end | data | animation | purpose\n\n"
        "Then add: Caption Groups (Final)\n"
        "Each row: group_id | words | start | end | duration\n\n"
        "Must strictly follow provided mapping.\n"
    )

    return f"SYSTEM:\n{system_content}\nUSER:\n{user_content}"


def build_prompt_for_pattern1_007() -> str:
    """Convenience builder for the pattern1_007 sample."""
    schema_path = Path("vasp/schemas/element_capability_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    word_map_path = Path("assets/inputs/song_0063_whisper.json")
    word_timing_map = json.loads(word_map_path.read_text(encoding="utf-8"))
    transcript = " ".join(str(x.get("text", "")).strip() for x in word_timing_map).strip()

    image_data = [
        {
            "id": "image_1",
            "path": "assets/inputs/images/990890291_afc72be141.jpg",
            "timing": "0.000-7.813",
            "about": "A man is doing a wheelie on a mountain bike.",
            "aim": "Cover frame horizontally when mentioned, then fade out as next topic starts.",
        },
        {
            "id": "image_2",
            "path": "assets/inputs/images/947969010_f1ea572e89.jpg",
            "timing": "7.813-15.626",
            "about": "The dog is climbing out of the water with a stick.",
            "aim": "Cover frame horizontally when mentioned, then fade out as next topic starts.",
        },
        {
            "id": "image_3",
            "path": "assets/inputs/images/873633312_a756d8b381.jpg",
            "timing": "15.626-23.439",
            "about": "A child wearing a white, red, and black life jacket was bounced into the air by something big and yellow.",
            "aim": "Cover frame horizontally when mentioned, then fade out as next topic starts.",
        },
    ]
    audio_data = [{"id": "audio_1", "path": "assets/inputs/song_0063.m4a", "timing": "0.000-23.439"}]
    current_video_state = {
        "canvas": {"width": 1080, "height": 1920},
        "duration": 23.439,
        "notes": "Keep all visual elements fully inside frame. Avoid harmful overlaps. Keep captions readable.",
    }

    return build_planner_prompt_with_schema(
        element_schema=schema,
        current_video_state=current_video_state,
        transcript=transcript,
        word_timing_map=word_timing_map,
        image_data=image_data,
        audio_data=audio_data,
        allowed_animations=["fade in/out", "jump in/out", "roll in/out"],
        pause_threshold=0.35,
    )
