from __future__ import annotations

import json
from pathlib import Path


def generate_combined_planner_input_prompt(
    *,
    system_prompt_path: str | Path,
    transcript: str | None,
    user_instruction: str,
    element3_path: str | Path,
    output_schema_path: str | Path,
    output_prompt_path: str | Path = "output/planner_combined_prompt_v2.txt",
    user_specific_instruction: str | None = None,
    media_json_path: str | Path = "output/media.json",
) -> Path:
    """Generate planner input prompt in the required flow sequence.

    Flow order:
    1) [System prompt]
    2) [Transcript]
    3) [User specific instruction (optional)]
    4) [element3.txt]
    5) [output_schema]
    """
    sp = Path(system_prompt_path)
    e3 = Path(element3_path)
    oschema = Path(output_schema_path)
    out = Path(output_prompt_path)
    media_json = Path(media_json_path)

    if not sp.exists():
        raise FileNotFoundError(f"System prompt file not found: {sp}")
    if not e3.exists():
        raise FileNotFoundError(f"element3 file not found: {e3}")
    if not oschema.exists():
        raise FileNotFoundError(f"Output schema file not found: {oschema}")

    system_prompt = sp.read_text(encoding="utf-8").strip()
    element3_text = e3.read_text(encoding="utf-8").strip()
    output_schema_text = oschema.read_text(encoding="utf-8").strip()
    transcript_text = (transcript or "").strip()
    if not transcript_text:
        transcript_text = _extract_transcript_from_media_json(media_json)
    instruction_text = (user_instruction or "").strip()
    theme_text = (user_specific_instruction or "").strip()

    if not transcript_text:
        raise ValueError(
            "Transcript cannot be empty. Pass transcript explicitly or provide media.json with transcript.full_text."
        )
    if not instruction_text:
        raise ValueError("user_instruction cannot be empty.")

    combined = (
        f"{system_prompt}\n\n"
        f"User instruction: {instruction_text}\n"
        f"Transcript: \"{transcript_text}\"\n\n"
    )
    if theme_text:
        combined += f"{theme_text}\n\n"
    combined += f"{element3_text}\n\n{output_schema_text}\n"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(combined, encoding="utf-8")
    return out


def _extract_transcript_from_media_json(media_json_path: Path) -> str:
    if not media_json_path.exists():
        return ""
    try:
        payload = json.loads(media_json_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    analysis = ((payload.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return ""
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        t = block.get("transcript")
        if not isinstance(t, dict):
            continue
        ft = t.get("full_text")
        if isinstance(ft, str) and ft.strip():
            return ft.strip()
    return ""
