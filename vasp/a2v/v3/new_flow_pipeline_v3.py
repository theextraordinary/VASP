from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from vasp.a2v.v2.creativity_policy import (
    CREATIVITY_LEVELS,
    get_creativity_policy,
)
from vasp.a2v.v2.design_presets_v3 import choose_refiner_design_preset
from vasp.a2v.v2.dynamic_prompt_generator import generate_dynamic_prompt_set, load_prompt_set
from vasp.a2v.v2.media_cropper import apply_crop_directives_to_captions_file
from vasp.a2v.v2.optional_media_collector import MODES as OPTIONAL_MEDIA_MODES
from vasp.a2v.v2.optional_media_collector import OPTIONAL_MEDIA_MAX_COUNT, OPTIONAL_MEDIA_MIN_COUNT
from vasp.a2v.v2.optional_media_collector import collect_optional_media
from vasp.a2v.v2.optional_media_collector import promote_crawled_data_to_library
from vasp.a2v.v2.preset_backgrounds_v3 import preset_background_prompt_text
from vasp.a2v.v2.progress_bar import ProgressBar
from vasp.a2v.v2.refiner_presets_v3 import list_refiner_presets
from vasp.a2v.v3.inter_generator import generate_inter_from_refined_segments
from vasp.a2v.v3.render_into_video import render_into_video
from vasp.a2v.v3.segment_generator import generate_segments_from_planner_matches
from vasp.a2v.v3.utils import (
    call_llm_endpoint,
    extract_transcript,
    is_visual_media,
    media_inputs,
    parse_jsonish,
    parse_jsonish_file,
    read_text,
    safe_name,
    write_json,
    write_text,
)
from vasp.media_reader.from_captions import create_media_json_from_captions_file


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_MEDIA_AIM = "use with appropriate captions"


def _quiet_call(log_path: Path, fn: Any, *args: Any, quiet: bool = True, **kwargs: Any) -> Any:
    if not quiet:
        return fn(*args, **kwargs)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", errors="ignore") as log:
        try:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                return fn(*args, **kwargs)
        except Exception:
            print(f"\nDetailed logs saved to: {log_path}")
            raise


def _split_words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", str(text or "").strip()) if w]


def _transcript_dicts(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if isinstance(analysis, dict):
        for block in analysis.values():
            if not isinstance(block, dict):
                continue
            transcript = block.get("transcript")
            if isinstance(transcript, dict):
                out.append(transcript)
    return out


def _apply_corrected_transcript(media_json: dict[str, Any], original: str, corrected: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    original_words = _split_words(original)
    corrected_words = _split_words(corrected)
    media_context = media_json.setdefault("media_context", {})
    media_context["transcript"] = corrected
    same_word_count = len(original_words) == len(corrected_words) and bool(corrected_words)

    for transcript in _transcript_dicts(media_json):
        transcript["full_text"] = corrected
        transcript["text"] = corrected
        if not same_word_count:
            continue
        timed_words = transcript.get("word_timing_map") or transcript.get("words")
        if isinstance(timed_words, list):
            word_i = 0
            for word_row in timed_words:
                if not isinstance(word_row, dict):
                    continue
                if word_i >= len(corrected_words):
                    break
                if "text" in word_row:
                    word_row["text"] = corrected_words[word_i]
                elif "word" in word_row:
                    word_row["word"] = corrected_words[word_i]
                word_i += 1
        groups = transcript.get("caption_groups")
        if isinstance(groups, list):
            cursor = 0
            for group in groups:
                if not isinstance(group, dict):
                    continue
                count = len(_split_words(str(group.get("text") or "")))
                if count <= 0:
                    continue
                group["text"] = " ".join(corrected_words[cursor : cursor + count])
                cursor += count
    if not same_word_count:
        warnings.append(
            f"edited_transcript_word_count_changed: original={len(original_words)} corrected={len(corrected_words)}; timing text was not fully remapped"
        )
    return media_json, warnings


def validate_transcript_word_replacements(original: str, corrected: str) -> list[str]:
    """Validate that transcript edits only replace words, never add/delete them."""
    original_words = _split_words(original)
    corrected_words = _split_words(corrected)
    errors: list[str] = []
    if len(original_words) != len(corrected_words):
        errors.append(f"word_count_changed: original={len(original_words)} corrected={len(corrected_words)}")
    if not corrected_words and original_words:
        errors.append("corrected_transcript_empty")
    return errors


def _apply_transcript_txt_corrections(media_json: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    transcript = extract_transcript(media_json)
    transcript_path = run_dir / "transcript.txt"
    write_text(run_dir / "transcript.generated.txt", transcript)
    print("\n[A2V_V3] Generated transcript:")
    print(transcript)
    print(f"[A2V_V3] Editable transcript file: {transcript_path}")
    print("[A2V_V3] To correct ASR words safely, stop now, edit transcript.txt without adding/deleting words, then rerun.")

    if not transcript_path.exists():
        write_text(transcript_path, transcript)
        write_json(
            run_dir / "transcript_correction_report.json",
            {
                "applied": False,
                "reason": "created_transcript_txt_first_run",
                "transcript_path": str(transcript_path),
            },
        )
        return media_json

    corrected = transcript_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not corrected and transcript:
        write_text(transcript_path, transcript)
        write_json(
            run_dir / "transcript_correction_report.json",
            {
                "applied": False,
                "reason": "populated_empty_transcript_txt_from_generated_transcript",
                "transcript_path": str(transcript_path),
            },
        )
        print("[A2V_V3] transcript.txt was empty; populated it from generated transcript. Edit it and rerun to apply corrections.")
        return media_json

    if not corrected or corrected == transcript:
        write_json(
            run_dir / "transcript_correction_report.json",
            {
                "applied": False,
                "reason": "no_user_correction_found",
                "transcript_path": str(transcript_path),
            },
        )
        return media_json

    errors = validate_transcript_word_replacements(transcript, corrected)
    if errors:
        write_json(
            run_dir / "transcript_correction_report.json",
            {
                "applied": False,
                "reason": "invalid_user_correction",
                "errors": errors,
                "transcript_path": str(transcript_path),
            },
        )
        print("[A2V_V3] transcript.txt correction ignored: " + "; ".join(errors))
        return media_json

    media_json, warnings = _apply_corrected_transcript(media_json, transcript, corrected)
    changed = sum(1 for a, b in zip(_split_words(transcript), _split_words(corrected)) if a != b)
    write_json(
        run_dir / "transcript_correction_report.json",
        {
            "applied": True,
            "changed_words": changed,
            "warnings": warnings,
            "transcript_path": str(transcript_path),
        },
    )
    print(f"[A2V_V3] Applied transcript.txt word replacements: changed_words={changed}")
    return media_json


def _maybe_edit_transcript_interactively(
    media_json: dict[str, Any],
    run_dir: Path,
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    transcript = extract_transcript(media_json)
    write_text(run_dir / "transcript_original.txt", transcript)
    if not enabled or not sys.stdin.isatty():
        return media_json
    print("\n\nEditable transcript")
    print("-" * 72)
    print(transcript)
    print("-" * 72)
    print("If the transcript is correct, press Enter.")
    print("If small word corrections are needed, paste the corrected transcript as one line and press Enter.")
    corrected = input("Corrected transcript > ").strip()
    if not corrected or corrected == transcript:
        write_text(run_dir / "transcript_corrected.txt", transcript)
        return media_json
    media_json, warnings = _apply_corrected_transcript(media_json, transcript, corrected)
    write_text(run_dir / "transcript_corrected.txt", corrected)
    if warnings:
        write_json(run_dir / "transcript_edit_warnings.json", warnings)
        print("Transcript updated, but timing remap warning saved to transcript_edit_warnings.json")
    else:
        print("Transcript corrections applied to full text, word timing text, and caption groups.")
    return media_json


def _visual_media_lines(media_json: dict[str, Any]) -> tuple[str, str, set[str]]:
    mandatory: list[str] = []
    mandatory_ids: set[str] = set()
    seen_about_aim: set[tuple[str, str]] = set()
    for row in media_inputs(media_json):
        if not isinstance(row, dict) or not is_visual_media(row):
            continue
        eid = str(row.get("id") or "")
        mt = str(row.get("media_type") or "")
        about = str(row.get("about") or "").strip()
        aim = str(row.get("aim") or DEFAULT_MEDIA_AIM).strip()
        dedupe_key = (
            mt.lower().strip(),
            re.sub(r"\s+", " ", about.lower()).strip(),
            re.sub(r"\s+", " ", aim.lower()).strip(),
        )
        if dedupe_key in seen_about_aim:
            continue
        seen_about_aim.add(dedupe_key)
        line = f"{eid} | {mt} | about: {about or '-'} | aim: {aim or DEFAULT_MEDIA_AIM}"
        mandatory.append(line)
        mandatory_ids.add(eid)
    return "\n".join(mandatory) or "(none)", "(none)", mandatory_ids


def _normalize_missing_media_aims(media_json: dict[str, Any]) -> dict[str, Any]:
    for row in media_inputs(media_json):
        if not isinstance(row, dict) or not is_visual_media(row):
            continue
        aim = str(row.get("aim") or "").strip()
        if not aim or aim.lower() in {"none", "null", "n/a", "na", "-"}:
            row["aim"] = DEFAULT_MEDIA_AIM
    return media_json


def _next_media_id(existing_ids: set[str]) -> str:
    max_num = 0
    for eid in existing_ids:
        if not eid.startswith("media_"):
            continue
        try:
            max_num = max(max_num, int(eid.split("_", 1)[1]))
        except Exception:
            continue
    while True:
        max_num += 1
        candidate = f"media_{max_num}"
        if candidate not in existing_ids:
            return candidate


def _add_optional_media_to_media_json(media_json: dict[str, Any], optional_media: list[dict[str, Any]]) -> dict[str, Any]:
    if not optional_media:
        return media_json
    media_context = media_json.setdefault("media_context", {})
    inputs = media_context.setdefault("inputs", [])
    probe = media_context.setdefault("probe", {})
    analysis = media_context.setdefault("analysis", {})
    existing = {str(row.get("id")) for row in inputs if isinstance(row, dict)}
    for item in optional_media:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        eid = _next_media_id(existing)
        item["element_id"] = eid
        inputs.append(
            {
                "id": eid,
                "path": path.replace("\\", "/"),
                "media_type": str(item.get("type") or "image"),
                "role": "supporting_visual",
                "aim": str(item.get("aim") or DEFAULT_MEDIA_AIM),
                "about": str(item.get("about") or ""),
                "source_about": str(item.get("source_about") or ""),
                "selection_reason": str(item.get("selection_reason") or ""),
                "transcript_part": str(item.get("transcript_part") or ""),
                "tags": ["library_selected", str(item.get("source") or "")],
            }
        )
        probe[eid] = {
            "duration": item.get("duration"),
            "width": item.get("width"),
            "height": item.get("height"),
        }
        analysis[eid] = {
            "transcript": None,
            "silence_regions": None,
            "scene_boundaries": None,
            "keyframes": None,
            "media_tags": ["library_selected", str(item.get("source") or "")],
            "warnings": [],
            "summary": str(item.get("about") or ""),
        }
        existing.add(eid)
    return media_json


def _format_visual_media_for_aim_refinement(media_json: dict[str, Any]) -> str:
    lines = ["media_id,type,about"]
    for row in media_inputs(media_json):
        if not isinstance(row, dict) or not is_visual_media(row):
            continue
        if not str(row.get("aim") or "").strip():
            row["aim"] = DEFAULT_MEDIA_AIM
        eid = str(row.get("id") or "").strip()
        mt = str(row.get("media_type") or "").strip()
        about = str(row.get("about") or "").replace("\n", " ").replace('"', "'").strip()
        lines.append(f'{eid},{mt},"{about}"')
    return "\n".join(lines)


def _apply_media_aim_updates(
    media_json: dict[str, Any],
    updates: list[Any],
    debug_dir: Path,
    *,
    label: str,
) -> dict[str, Any]:
    rows_by_id = {
        str(row.get("id") or ""): row
        for row in media_inputs(media_json)
        if isinstance(row, dict) and is_visual_media(row)
    }
    applied: list[dict[str, Any]] = []
    for item in updates:
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("media_id") or item.get("element_id") or "").strip()
        row = rows_by_id.get(media_id)
        if not row:
            continue
        aim = str(item.get("aim") or "").strip()
        about = str(item.get("about") or "").strip()
        transcript_part = str(item.get("transcript_part") or item.get("text") or "").strip()
        match_strength = str(item.get("match_strength") or item.get("strength") or "").strip()
        strong_property = str(item.get("strong_property") or item.get("match_property") or "").strip()
        reason = str(item.get("reason") or item.get("match_reason") or "").strip()
        if about:
            row["about"] = about
        if transcript_part:
            row["transcript_part"] = transcript_part
            row["aim"] = f"show during \"{transcript_part}\""
        elif aim:
            cleaned = aim
            row["aim"] = cleaned if cleaned.lower().startswith("show during") else f"show during \"{cleaned}\""
        if reason:
            row["selection_reason"] = reason
        if match_strength:
            row["match_strength"] = match_strength
        if strong_property:
            row["strong_property"] = strong_property
        applied.append(
            {
                "media_id": media_id,
                "about": row.get("about", ""),
                "aim": row.get("aim", ""),
                "transcript_part": row.get("transcript_part", ""),
                "match_strength": row.get("match_strength", ""),
                "strong_property": row.get("strong_property", ""),
                "reason": row.get("selection_reason", ""),
            }
        )
    write_json(debug_dir / f"{label}_updates.json", {"media_updates": applied})
    return media_json


def _parse_media_updates_response(raw: str, debug_dir: Path, *, label: str) -> list[Any] | None:
    obj = parse_jsonish(raw)
    if not isinstance(obj, dict):
        repaired_raw = re.sub(r'\{\s*"(media_\d+)"\s*,', r'{"media_id":"\1",', raw)
        if repaired_raw != raw:
            write_text(debug_dir / f"{label}_response.repaired.txt", repaired_raw)
            obj = parse_jsonish(repaired_raw)
    updates = obj.get("media_updates") if isinstance(obj, dict) else None
    return updates if isinstance(updates, list) else None


def _refine_mandatory_media_aims_with_base_planner(
    media_json: dict[str, Any],
    transcript: str,
    user_instruction: str,
    base_planner_endpoint: str | None,
    debug_dir: Path,
    *,
    max_tokens: int = 4000,
) -> dict[str, Any]:
    mandatory_media_csv = _format_visual_media_for_aim_refinement(media_json)
    prompt = "\n\n".join(
        [
            "You are a Media Aim Refinement Planner for a short-form video editor.",
            "Your job is to make the MANDATORY MEDIA section more useful before the main planner sees it.",
            "Return valid JSON only.",
            "For every media_id in MANDATORY MEDIA, create a distinct placement-oriented aim using the transcript.",
            "If multiple media share the same broad query/about, assign them to different transcript beats or different editor uses.",
            "The transcript_part field must be unique for every media item. Never repeat the same transcript_part across two media.",
            "If two media fit the same phrase, assign one to a nearby earlier/later phrase or a different emotional/editorial use.",
            "Choose the strongest transcript part for each media: prefer exact named person/object/action/emotion matches over generic related phrases.",
            "Add strong_property describing why the chosen transcript part is strong, such as exact_person, exact_object, action_match, emotional_reaction, visual_metaphor, contextual_support, or fallback.",
            "If the match is weak but required, still choose the closest useful transcript part and set match_strength to low.",
            "Aim should say exactly when to show the media, preferably naming an exact transcript phrase.",
            "Do not invent media ids. Do not remove media. Do not output markdown.",
            "Output schema:",
            '{"media_updates":[{"media_id":"media_5","about":"short visual description or original topic","aim":"show during exact transcript phrase ...","transcript_part":"exact transcript phrase","match_strength":"high|medium|low","strong_property":"exact_object|action_match|emotional_reaction|contextual_support|fallback","reason":"why this placement is useful"}]}',
            f"USER INSTRUCTION:\n{user_instruction}",
            f"FULL TRANSCRIPT:\n{transcript}",
            "MANDATORY MEDIA:\n" + mandatory_media_csv,
        ]
    )
    prompt_path = write_text(debug_dir / "media_aim_refinement_prompt.txt", prompt)
    print(f"[A2V_V3] wrote media aim refinement prompt: {prompt_path}")
    if not base_planner_endpoint:
        write_text(debug_dir / "media_aim_refinement_response.txt", "")
        print("[A2V_V3] no base planner endpoint for media aim refinement; keeping existing aims.")
        return media_json
    try:
        raw = call_llm_endpoint(base_planner_endpoint, prompt, temperature=0.0, max_tokens=max_tokens)
    except Exception as exc:
        write_text(debug_dir / "media_aim_refinement_response.txt", f"ERROR: {exc}")
        print(f"[A2V_V3] media aim refinement failed; keeping existing aims: {exc}")
        return media_json
    write_text(debug_dir / "media_aim_refinement_response.txt", raw)
    updates = _parse_media_updates_response(raw, debug_dir, label="media_aim_refinement")
    if updates is None:
        write_json(debug_dir / "media_aim_refinement_updates.json", {"media_updates": [], "warning": "invalid_response"})
        print("[A2V_V3] media aim refinement returned invalid JSON; keeping existing aims.")
        return media_json

    media_json = _apply_media_aim_updates(media_json, updates, debug_dir, label="media_aim_refinement")
    applied = json.loads((debug_dir / "media_aim_refinement_updates.json").read_text(encoding="utf-8")).get("media_updates", [])
    print(f"[A2V_V3] media aim refinement applied updates={len(applied)}")
    return media_json


def _assign_media_aims_with_base_planner(
    media_json: dict[str, Any],
    transcript: str,
    user_instruction: str,
    base_planner_endpoint: str | None,
    debug_dir: Path,
) -> dict[str, Any]:
    media_csv = _format_visual_media_for_aim_refinement(media_json)
    prompt = "\n".join(
        [
            "You are Transcript-Media Assignment Planner.",
            "",
            "Task:",
            "Assign EXACTLY one transcript span to EACH media row.",
            "",
            "Output:",
            "Return ONE valid JSON object only.",
            "No markdown.",
            "No extra keys.",
            "No explanations.",
            "",
            "Rules:",
            "- Use every media_id exactly once.",
            "- Output ONLY fields defined in schema.",
            "- NEVER output about, aim, type, or extra fields.",
            "- transcript_part MUST be copied EXACTLY from TRANSCRIPT.",
            "- transcript_part MUST be a real substring from TRANSCRIPT.",
            "- NEVER invent, paraphrase, summarize, or modify transcript text.",
            "- NEVER copy MEDIA_ROWS.about into transcript_part unless those exact words appear in TRANSCRIPT.",
            "- MEDIA_ROWS.about exists ONLY to understand media meaning.",
            "- Prefer short meaningful phrases (2-12 words).",
            "- Avoid whole sentences unless necessary.",
            "- Each transcript_part must be unique and non-overlapping.",
            "- Strongly prefer semantic matching over nearest-word matching.",
            "",
            "Match order:",
            "1 exact person/object",
            "2 exact action",
            "3 emotion/reaction",
            "4 contextual support",
            "5 fallback",
            "",
            "Examples:",
            "",
            "BAD:",
            'about="war area"',
            'transcript_part="war area"',
            "",
            "GOOD:",
            'transcript_part="North Vietnamese forces launched the final offensive"',
            "",
            "BAD:",
            'about="slavery shown in funny way"',
            'transcript_part="slavery shown in funny way"',
            "",
            "GOOD:",
            'transcript_part="made slave trading illegal"',
            "",
            "BAD:",
            'about="person saying i am free"',
            'transcript_part="i am free"',
            "",
            "GOOD:",
            'transcript_part="made slave trading illegal in the United Kingdom"',
            "",
            "FINAL VALIDATION:",
            "Before output check:",
            "",
            "- every media_id used exactly once",
            "- transcript_part exists EXACTLY in TRANSCRIPT",
            "- no transcript_part copied from about unless present in TRANSCRIPT",
            "- no overlapping spans",
            "- remove any invented fields",
            "- output schema only",
            "",
            f"USER_INSTRUCTION: {user_instruction}",
            f"TRANSCRIPT: {transcript}",
            "MEDIA_ROWS:",
            media_csv,
            "",
            "Schema:",
            "{",
            ' "media_updates":[',
            "   {",
            '     "media_id":"media_2",',
            '     "transcript_part":"exact transcript words",',
            '     "match_strength":"high|medium|low",',
            '     "strong_property":"exact_object|action_match|emotional_reaction|contextual_support|fallback",',
            '     "reason":"short"',
            "   }",
            " ]",
            "}",
        ]
    )
    prompt_path = write_text(debug_dir / "aim_refinement_prompt.txt", prompt)
    print(f"[A2V_V3] wrote aim refinement prompt: {prompt_path}")
    if not base_planner_endpoint:
        write_text(debug_dir / "aim_refinement_response.txt", "")
        write_json(debug_dir / "aim_refinement_updates.json", {"media_updates": [], "warning": "base_planner_endpoint_missing"})
        print("[A2V_V3] no base planner endpoint for aim refinement; keeping existing aims.")
        return media_json
    try:
        raw = call_llm_endpoint(base_planner_endpoint, prompt, temperature=0.0, max_tokens=3000)
    except Exception as exc:
        write_text(debug_dir / "aim_refinement_response.txt", f"ERROR: {exc}")
        write_json(debug_dir / "aim_refinement_updates.json", {"media_updates": [], "warning": str(exc)})
        print(f"[A2V_V3] aim refinement failed; keeping existing aims: {exc}")
        return media_json
    write_text(debug_dir / "aim_refinement_response.txt", raw)
    updates = _parse_media_updates_response(raw, debug_dir, label="aim_refinement")
    if updates is None:
        write_json(debug_dir / "aim_refinement_updates.json", {"media_updates": [], "warning": "invalid_response"})
        print("[A2V_V3] aim refinement returned invalid JSON; keeping existing aims.")
        return media_json
    media_json = _apply_media_aim_updates(media_json, updates, debug_dir, label="aim_refinement")
    applied = json.loads((debug_dir / "aim_refinement_updates.json").read_text(encoding="utf-8")).get("media_updates", [])
    print(f"[A2V_V3] aim refinement applied updates={len(applied)}")
    return media_json


def _correct_transcript_with_base_planner(
    media_json: dict[str, Any],
    user_instruction: str,
    base_planner_endpoint: str | None,
    debug_dir: Path,
) -> dict[str, Any]:
    transcript = extract_transcript(media_json)
    if not transcript or not base_planner_endpoint:
        return media_json
    prompt = "\n\n".join(
        [
            "You are a transcript correction assistant for short-form video planning.",
            "Fix obvious ASR mistakes, unusual words, broken sentence fragments, and punctuation.",
            "Keep the same meaning. Do not summarize. Do not add facts.",
            "Prefer keeping the same word count when possible so caption timings stay aligned.",
            "Return valid JSON only.",
            '{"corrected_transcript":"full corrected transcript here","notes":["short note"]}',
            f"USER INSTRUCTION:\n{user_instruction}",
            f"RAW TRANSCRIPT:\n{transcript}",
        ]
    )
    write_text(debug_dir / "base_transcript_correction_prompt.txt", prompt)
    try:
        raw = call_llm_endpoint(base_planner_endpoint, prompt, temperature=0.0, max_tokens=1800)
    except Exception as exc:
        write_text(debug_dir / "base_transcript_correction_response.txt", f"ERROR: {exc}")
        return media_json
    write_text(debug_dir / "base_transcript_correction_response.txt", raw)
    obj = parse_jsonish(raw)
    corrected = str((obj or {}).get("corrected_transcript") or "").strip()
    if not corrected or corrected == transcript:
        return media_json
    media_json, warnings = _apply_corrected_transcript(media_json, transcript, corrected)
    write_text(debug_dir / "base_transcript_corrected.txt", corrected)
    if warnings:
        write_json(debug_dir / "base_transcript_correction_warnings.json", warnings)
    return media_json


def _build_planner_prompt(
    media_json: dict[str, Any],
    user_instruction: str,
    prompt_set: dict[str, str] | None = None,
) -> tuple[str, set[str]]:
    prompt_set = prompt_set or load_prompt_set(PROMPT_DIR)
    mandatory, optional, mandatory_ids = _visual_media_lines(media_json)
    body = read_text(PROMPT_DIR / "planner_prompt.md").format(
        user_instruction=user_instruction,
        full_transcript=extract_transcript(media_json),
        mandatory_media=mandatory,
        optional_media=optional,
    )
    prompt = "\n\n".join([prompt_set["planner_sp"], body, prompt_set["planner_os"]])
    return prompt, mandatory_ids


def _sanitize_planner_output_media_ids(obj: dict[str, Any], mandatory_ids: set[str]) -> list[str]:
    warnings: list[str] = []
    allowed_ids = mandatory_ids
    matches = obj.get("matches")
    if not isinstance(matches, list):
        return warnings
    clean_matches: list[dict[str, Any]] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        media_id = str(m.get("media_id") or "").strip()
        if media_id not in allowed_ids:
            warnings.append(f"removed_invented_media_id:{media_id or '(empty)'}")
            continue
        m["mandatory_media"] = True
        clean_matches.append(m)
    obj["matches"] = clean_matches
    return warnings


def _validate_planner_output(obj: dict[str, Any], transcript: str, mandatory_ids: set[str]) -> list[str]:
    warnings: list[str] = []
    matches = obj.get("matches")
    if not isinstance(matches, list):
        return ["planner matches missing or not list"]
    used = {str(m.get("media_id")) for m in matches if isinstance(m, dict)}
    for mid in sorted(mandatory_ids - used):
        warnings.append(f"mandatory_media_not_used:{mid}")
    norm_transcript = transcript.lower()
    for m in matches:
        if not isinstance(m, dict):
            continue
        text = str(m.get("text", "")).strip()
        if text and text.lower() not in norm_transcript:
            warnings.append(f"match_text_not_exact_substring:{text[:40]}")
    return warnings


def _default_refined_segment(segment_obj: dict[str, Any], warnings: list[str], creativity_level: int = 2) -> dict[str, Any]:
    ts = float(segment_obj.get("t_start", 0.0) or 0.0)
    te = float(segment_obj.get("t_end", ts) or ts)
    media = segment_obj.get("media") if isinstance(segment_obj.get("media"), dict) else {}
    media_id = str(segment_obj.get("media_id") or media.get("element_id") or "")
    has_visual_media = bool(media_id) and is_visual_media(media)
    is_caption_only = (
        not has_visual_media
        or "caption_only_unmatched_from_media_json" in set(segment_obj.get("warnings") or [])
    )
    preset = choose_refiner_design_preset(segment_obj, creativity_level, has_visual=not is_caption_only)
    captions = []
    for idx, g in enumerate(segment_obj.get("caption_groups", []) if isinstance(segment_obj.get("caption_groups"), list) else []):
        if not isinstance(g, dict):
            continue
        style = dict(preset["caption"])
        animation = style.pop("animation", {"type": "word_reveal", "intensity": "medium"})
        captions.append(
            {
                "caption_group_index": g.get("index"),
                "text": g.get("text"),
                "t_start": g.get("start"),
                "t_end": g.get("end"),
                "layout": dict(preset["caption_layout"]),
                "style": style,
                "highlight_words": [],
                "animation": animation,
            }
        )
    visual_timeline = []
    if not is_caption_only:
        visual_timeline.append(
            {
                "element_id": media_id,
                "source_ref": media_id,
                "type": media.get("type") or "image",
                "t_start": ts,
                "t_end": te,
                "layout": dict(preset["visual_layout"]),
                "transition_in": {"type": "fade", "duration": 0.15},
                "transition_out": {"type": "fade", "duration": 0.15},
                "animation": dict(preset["visual_animation"]),
            }
        )
    background = dict(preset["background"])
    background.update({"t_start": ts, "t_end": te, "reason": f"preset:{preset['name']}"})
    return {
        "segment_id": segment_obj.get("segment_id"),
        "creativity_level": creativity_level,
        "style_policy": {k: v for k, v in get_creativity_policy(creativity_level).items() if k != "rules_text"},
        "t_start": ts,
        "t_end": te,
        "background_timeline": [background],
        "caption_timeline": captions,
        "visual_timeline": visual_timeline,
        "warnings": warnings,
    }


def _build_refiner_prompt(
    segment_md: str,
    user_instruction: str,
    creativity_level: int = 2,
    use_preset_backgrounds: bool = True,
    prompt_set: dict[str, str] | None = None,
) -> str:
    prompt_set = prompt_set or load_prompt_set(PROMPT_DIR)
    policy = get_creativity_policy(creativity_level)
    preset_rules_path = Path(__file__).resolve().parents[1] / "prompts" / "refiner_v3_preset_rules.md"
    preset_rules = read_text(preset_rules_path) if preset_rules_path.exists() else ""
    preset_catalog_obj = list_refiner_presets()
    preset_catalog = json.dumps(preset_catalog_obj, ensure_ascii=False, indent=2)
    preset_contract = "\n".join(
        [
            "REQUIRED PRESET OUTPUT CONTRACT:",
            "You must fill these top-level fields using only names from AVAILABLE REFINER PRESETS:",
            "preset_bundle, background_preset, caption_preset, caption_layout_preset, visual_layout_preset, caption_animation_preset, visual_animation_preset, transition_preset.",
            "For caption-only segments, set visual_timeline to [] and choose caption_only_center or caption_only_lower_center.",
            "For visual segments, use caption_bottom_safe unless creativity is 5 and another layout is clearly better.",
            "Use preset_bundle as the main whole-segment style decision.",
            "Timeline items may repeat preset names for local variation, but should inherit from the top-level preset fields by default.",
            "Only use raw override fields for small safe changes, and only choose enum values from the output schema.",
            "Allowed transition override types: none, fade, cut, pop, slide, zoom, zoom_blur, blur_fade, whip, flash, dip.",
            "Allowed caption animation override types: word_reveal, fade, pop, slide_up, typewriter, bounce, blur_in, glow_pulse, stomp, wave_reveal, none.",
            "Allowed visual animation override types: none, subtle_zoom, subtle_zoom_out, pulse, float, drift, card_lift, tilt_float, shake.",
            f"Valid preset_bundle names: {', '.join(preset_catalog_obj['preset_bundles'])}",
        ]
    )
    preset_background_contract = "\n".join(
        [
            f"USE PRESET BACKGROUNDS: {str(use_preset_backgrounds).lower()}",
            preset_background_prompt_text() if use_preset_backgrounds else "Preset background images are disabled. Create background_timeline normally.",
            "When use_preset_backgrounds=true, choose background_image_preset as bg1, bg2, bg3, bg4, or bg5.",
            "Also put background_image_preset on each background_timeline row when that row should use a preset image.",
            "Use bg1 or bg5 for light informative parts, bg2 for dark informative parts, bg3 when a visual is centered, and bg4 when captions are centered.",
        ]
    )
    return "\n\n".join(
        [
            prompt_set["refiner_sp"],
            "CREATIVITY POLICY:\n" + policy["rules_text"],
            "PROFESSIONAL PRESET RULES:\n" + preset_rules,
            preset_background_contract,
            "AVAILABLE REFINER PRESETS:\n" + preset_catalog,
            preset_contract,
            "Prefer selecting preset names instead of inventing raw styles.",
            f"USER INSTRUCTION:\n{user_instruction}",
            "SEGMENT:\n" + segment_md,
            prompt_set["refiner_os"],
        ]
    )


def run_new_flow_pipeline_v3(
    captions_path: str | Path,
    user_instruction: str,
    planner_endpoint: str,
    refiner_endpoint: str,
    edit_name: str,
    output_dir: str | Path = "output/a2v_v3",
    creativity: int = 2,
    media_collection_mode: str = "none",
    asset_library_dir: str | Path = "assets/library",
    collected_assets_dir: str | Path = "assets/crawled_data",
    optional_media_count: int = 10,
    crawl_total_per_query: int = 8,
    crawl_funny_percent: int = 30,
    base_planner_endpoint: str | None = None,
    use_preset_backgrounds: bool = True,
    verbose: bool = False,
    edit_transcript: bool = False,
    refine_crawl_media_aims: bool = False,
    aim_refinement: bool = False,
    dynamic_prompts: bool = False,
    render_captions: bool = True,
) -> dict[str, str]:
    policy = get_creativity_policy(creativity)
    run_dir = Path(output_dir) / safe_name(edit_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    media_json_path = run_dir / "media.json"
    verbose_log_path = run_dir / "pipeline_verbose.log"
    progress = ProgressBar(total=9)
    progress.render(f"Starting A2V V3: {safe_name(edit_name)}")
    if not verbose:
        write_text(
            verbose_log_path,
            "\n".join(
                [
                    f"run_dir={run_dir}",
                    f"creativity={creativity}",
                    f"use_preset_backgrounds={use_preset_backgrounds}",
                    f"render_captions={render_captions}",
                    f"captions_path={captions_path}",
                    f"asset_library_dir={asset_library_dir}",
                    "",
                ]
            ),
        )
    creativity_policy_path = write_json(run_dir / "creativity_policy.json", policy)
    crop_report = _quiet_call(
        verbose_log_path,
        apply_crop_directives_to_captions_file,
        captions_path,
        quiet=not verbose,
    )
    crop_report_path = write_json(run_dir / "media_crop_report.json", crop_report)
    prompt_set = load_prompt_set(PROMPT_DIR)
    dynamic_prompt_dir = run_dir / "dynamic_prompts"
    dynamic_prompt_report: dict[str, Any] = {"enabled": False, "used_dynamic_prompts": False}
    if dynamic_prompts:
        progress.render("Generating dynamic planner/refiner prompts")
        prompt_set, dynamic_prompt_report = _quiet_call(
            verbose_log_path,
            generate_dynamic_prompt_set,
            base_planner_endpoint=base_planner_endpoint,
            user_instruction=user_instruction,
            prompt_dir=PROMPT_DIR,
            output_dir=dynamic_prompt_dir,
            quiet=not verbose,
        )
        status = "dynamic" if dynamic_prompt_report.get("used_dynamic_prompts") else "fallback"
        progress.render(f"Dynamic prompts: {status}")
    media_json = _quiet_call(
        verbose_log_path,
        create_media_json_from_captions_file,
        captions_file_path=captions_path,
        output_media_json_path=media_json_path,
        instruction=user_instruction,
        quiet=not verbose,
    )
    progress.advance("Loaded media/captions")
    media_json = _normalize_missing_media_aims(media_json)
    media_json = _apply_transcript_txt_corrections(media_json, run_dir)
    if edit_transcript:
        write_text(
            run_dir / "transcript_edit_disabled.txt",
            "Interactive transcript editing is disabled because changing transcript text after timing extraction can break word/caption alignment.",
        )
    media_json_path.write_text(json.dumps(media_json, ensure_ascii=False, indent=2), encoding="utf-8")
    media_collection_mode = (media_collection_mode or "none").strip().lower()
    if media_collection_mode not in OPTIONAL_MEDIA_MODES:
        raise ValueError(f"media collection mode must be one of {sorted(OPTIONAL_MEDIA_MODES)}, got {media_collection_mode}")
    optional_media_debug_dir = run_dir / "optional_media"
    if media_collection_mode == "crawl":
        write_text(
            optional_media_debug_dir / "base_transcript_correction_disabled.txt",
            "Base-planner transcript correction is disabled because corrected text can desync Whisper word/caption timings.",
        )
    collected_assets_dir_resolved = str(collected_assets_dir).format(edit_name=safe_name(edit_name))
    selected_optional_media = _quiet_call(
        verbose_log_path,
        collect_optional_media,
        mode=media_collection_mode,
        transcript=extract_transcript(media_json),
        user_instruction=user_instruction,
        edit_name=safe_name(edit_name),
        base_planner_endpoint=base_planner_endpoint or planner_endpoint,
        asset_library_dir=asset_library_dir,
        collected_assets_dir=collected_assets_dir_resolved,
        optional_media_count=optional_media_count,
        crawl_total_per_query=crawl_total_per_query,
        crawl_funny_percent=crawl_funny_percent,
        debug_dir=optional_media_debug_dir,
        quiet=not verbose,
    )
    progress.advance(f"Optional media: mode={media_collection_mode}, selected={len(selected_optional_media)}")
    media_json = _add_optional_media_to_media_json(media_json, selected_optional_media)
    media_json = _normalize_missing_media_aims(media_json)
    if selected_optional_media:
        write_json(optional_media_debug_dir / "selected_optional_media_mapped.json", selected_optional_media)
    aim_refinement_dir = run_dir / "aim_refinement"
    if aim_refinement:
        aim_refinement_dir.mkdir(parents=True, exist_ok=True)
        media_json = _quiet_call(
            verbose_log_path,
            _assign_media_aims_with_base_planner,
            media_json=media_json,
            transcript=extract_transcript(media_json),
            user_instruction=user_instruction,
            base_planner_endpoint=base_planner_endpoint,
            debug_dir=aim_refinement_dir,
            quiet=not verbose,
        )
        write_json(aim_refinement_dir / "media_json_after_aim_refinement.json", media_json)
    elif media_collection_mode == "crawl" and refine_crawl_media_aims:
        aim_refinement_dir.mkdir(parents=True, exist_ok=True)
        media_json = _quiet_call(
            verbose_log_path,
            _refine_mandatory_media_aims_with_base_planner,
            media_json=media_json,
            transcript=extract_transcript(media_json),
            user_instruction=user_instruction,
            base_planner_endpoint=base_planner_endpoint,
            debug_dir=aim_refinement_dir,
            quiet=not verbose,
        )
        write_json(aim_refinement_dir / "media_json_after_aim_refinement.json", media_json)
    progress.advance("Prepared planner media aims")
    media_json_path.write_text(json.dumps(media_json, ensure_ascii=False, indent=2), encoding="utf-8")

    planner_prompt, mandatory_ids = _build_planner_prompt(media_json, user_instruction, prompt_set=prompt_set)
    planner_prompt_path = write_text(run_dir / "planner_prompt.txt", planner_prompt)
    progress.render("Calling Planner endpoint")
    planner_raw = call_llm_endpoint(planner_endpoint, planner_prompt, temperature=0.0, max_tokens=4000)
    write_text(run_dir / "planner_output.raw.txt", planner_raw)
    planner_obj = parse_jsonish(planner_raw) or {"planner_version": "v3_media_text_matching", "matches": [], "unmatched_text": [], "warnings": ["invalid planner json"]}
    planner_obj.setdefault("warnings", [])
    planner_obj["warnings"].extend(_sanitize_planner_output_media_ids(planner_obj, mandatory_ids))
    planner_obj["warnings"].extend(_validate_planner_output(planner_obj, extract_transcript(media_json), mandatory_ids))
    planner_output_path = write_json(run_dir / "planner_output.json", planner_obj)
    progress.advance(f"Planner returned {len(planner_obj.get('matches') or [])} matches")

    segment_dir = run_dir / "generated_segments"
    segment_paths = _quiet_call(
        verbose_log_path,
        generate_segments_from_planner_matches,
        planner_output_path,
        media_json_path,
        segment_dir,
        quiet=not verbose,
    )
    progress.advance(f"Generated {len(segment_paths)} segments")
    progress.set_total(progress.total + len(segment_paths))

    refiner_inputs = run_dir / "refiner_inputs"
    refiner_outputs = run_dir / "refiner_outputs"
    refiner_inputs.mkdir(parents=True, exist_ok=True)
    refiner_outputs.mkdir(parents=True, exist_ok=True)
    for idx, seg_path in enumerate(segment_paths, start=1):
        segment_md = seg_path.read_text(encoding="utf-8")
        refiner_prompt = _build_refiner_prompt(
            segment_md,
            user_instruction,
            creativity,
            use_preset_backgrounds,
            prompt_set=prompt_set,
        )
        in_path = write_text(refiner_inputs / f"{seg_path.stem}_refiner_input.txt", refiner_prompt)
        progress.render(f"Calling Refiner endpoint for segment {idx}/{len(segment_paths)}")
        raw = call_llm_endpoint(refiner_endpoint, refiner_prompt, temperature=0.0, max_tokens=2200)
        write_text(refiner_outputs / f"{seg_path.stem}.raw.txt", raw)
        obj = parse_jsonish(raw)
        segment_obj = parse_jsonish_file(seg_path) or {}
        if not isinstance(obj, dict):
            obj = _default_refined_segment(segment_obj, ["invalid_refiner_json_fallback"], creativity)
        else:
            # Keep renderer contract stable even if the model drifts.
            obj.setdefault("warnings", [])
            obj.setdefault("creativity_level", creativity)
            obj.setdefault("style_policy", {k: v for k, v in policy.items() if k != "rules_text"})
            if not isinstance(obj.get("visual_timeline"), list) or not obj.get("visual_timeline"):
                obj = _default_refined_segment(segment_obj, ["missing_visual_timeline_fallback"] + list(obj.get("warnings", [])), creativity)
        write_json(refiner_outputs / f"{seg_path.stem}.json", obj)
        if verbose:
            print(f"[A2V_V3] refined {seg_path.name} via {in_path.name}")
        progress.advance(f"Refined segment {idx}/{len(segment_paths)}")

    inter_path = _quiet_call(
        verbose_log_path,
        generate_inter_from_refined_segments,
        refiner_outputs,
        media_json_path,
        run_dir / "inter.json",
        creativity_level=creativity,
        use_preset_backgrounds=use_preset_backgrounds,
        render_captions=render_captions,
        quiet=not verbose,
    )
    progress.advance("Generated inter.json")
    progress.render("Rendering final video")
    video_path = _quiet_call(
        verbose_log_path,
        render_into_video,
        inter_path,
        media_json_path,
        run_dir / "insta_edit.mp4",
        quiet=not verbose,
    )
    progress.advance("Rendered final video")
    crawl_promotion_report = None
    if media_collection_mode == "crawl":
        crawl_promotion_report = _quiet_call(
            verbose_log_path,
            promote_crawled_data_to_library,
            crawled_data_dir=collected_assets_dir_resolved,
            asset_library_dir=asset_library_dir,
            debug_dir=optional_media_debug_dir,
            quiet=not verbose,
        )
    progress.finish("A2V V3 complete")

    return {
        "run_dir": str(run_dir),
        "media_json": str(media_json_path),
        "planner_prompt": str(planner_prompt_path),
        "planner_output": str(planner_output_path),
        "creativity_policy": str(creativity_policy_path),
        "media_crop_report": str(crop_report_path),
        "optional_media": str(optional_media_debug_dir),
        "aim_refinement": str(aim_refinement_dir) if aim_refinement or refine_crawl_media_aims else "",
        "dynamic_prompts": str(dynamic_prompt_dir) if dynamic_prompts else "",
        "segments_dir": str(segment_dir),
        "refiner_inputs": str(refiner_inputs),
        "refiner_outputs": str(refiner_outputs),
        "inter_json": str(inter_path),
        "video": str(video_path),
        "crawl_promotion_report": str(optional_media_debug_dir / "crawled_data_promotion_report.json") if crawl_promotion_report else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run A2V v3 media-text matching pipeline.")
    parser.add_argument("--captions-path", "--captions-file", "--transcript-file", dest="captions_path", required=True)
    parser.add_argument("--instruction", "--user-instruction", dest="instruction", required=True)
    parser.add_argument("--planner-endpoint", required=True)
    parser.add_argument("--refiner-endpoint", required=True)
    parser.add_argument("--edit-name", required=True)
    parser.add_argument("--output-dir", default="output/a2v_v3")
    parser.add_argument("--creativity", type=int, default=2, choices=CREATIVITY_LEVELS)
    parser.add_argument("--media-collection-mode", default="none", choices=sorted(OPTIONAL_MEDIA_MODES))
    parser.add_argument("--asset-library-dir", default="assets/library")
    parser.add_argument("--collected-assets-dir", default="assets/crawled_data")
    parser.add_argument("--optional-media-count", type=int, default=10, choices=range(OPTIONAL_MEDIA_MIN_COUNT, OPTIONAL_MEDIA_MAX_COUNT + 1))
    parser.add_argument("--crawl-total-per-query", type=int, default=8, help=argparse.SUPPRESS)
    parser.add_argument("--crawl-funny-percent", type=int, default=30, help=argparse.SUPPRESS)
    parser.add_argument("--base-planner-endpoint", default=None)
    parser.add_argument(
        "--dynamic-prompts",
        action="store_true",
        help="Use the base planner once to generate run-local planner/refiner SP/OS prompts from the user instruction.",
    )
    parser.add_argument(
        "--refine-crawl-media-aims",
        action="store_true",
        help="Run an extra base-planner pass to rewrite crawled media aims with unique transcript parts.",
    )
    parser.add_argument(
        "--aim-refinement",
        action="store_true",
        help="Run a base-planner pass before planner_prompt.txt to rewrite all visual media aims using exact transcript parts.",
    )
    parser.add_argument(
        "--use-preset-backgrounds",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use assets/preset_bgs/bg*.webp as refiner-selectable background images.",
    )
    parser.add_argument(
        "--edit-transcript",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Deprecated no-op. Transcript editing is disabled to preserve Whisper timing alignment.",
    )
    parser.add_argument(
        "--no-cpation",
        "--no-caption",
        dest="no_caption",
        action="store_true",
        help="Disable caption rendering in the final video/inter.json. Keeps transcript/caption timing available for planning.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs instead of writing them to pipeline_verbose.log.")
    args = parser.parse_args()
    result = run_new_flow_pipeline_v3(
        captions_path=args.captions_path,
        user_instruction=args.instruction,
        planner_endpoint=args.planner_endpoint,
        refiner_endpoint=args.refiner_endpoint,
        edit_name=args.edit_name,
        output_dir=args.output_dir,
        creativity=args.creativity,
        media_collection_mode=args.media_collection_mode,
        asset_library_dir=args.asset_library_dir,
        collected_assets_dir=args.collected_assets_dir,
        optional_media_count=args.optional_media_count,
        crawl_total_per_query=args.crawl_total_per_query,
        crawl_funny_percent=args.crawl_funny_percent,
        base_planner_endpoint=args.base_planner_endpoint,
        use_preset_backgrounds=args.use_preset_backgrounds,
        verbose=args.verbose,
        edit_transcript=args.edit_transcript,
        refine_crawl_media_aims=args.refine_crawl_media_aims,
        aim_refinement=args.aim_refinement,
        dynamic_prompts=args.dynamic_prompts,
        render_captions=not args.no_caption,
    )
    print(f"Video: {result['video']}")
    print(f"Run dir: {result['run_dir']}")


if __name__ == "__main__":
    main()
