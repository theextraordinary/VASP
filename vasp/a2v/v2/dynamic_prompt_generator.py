from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vasp.a2v.v3.utils import call_llm_endpoint, parse_jsonish, read_text, write_json, write_text


PLANNER_PROMPT_KEYS = ("planner_sp", "planner_os")
REFINER_PROMPT_KEYS = ("refiner_sp", "refiner_os")
PROMPT_KEYS = PLANNER_PROMPT_KEYS + REFINER_PROMPT_KEYS


def load_prompt_set(prompt_dir: str | Path) -> dict[str, str]:
    root = Path(prompt_dir)
    return {
        "planner_sp": read_text(root / "planner_sp.md"),
        "planner_os": read_text(root / "planner_os.md"),
        "refiner_sp": read_text(root / "refiner_sp.md"),
        "refiner_os": read_text(root / "refiner_os.md"),
    }


def _build_dynamic_prompt_request(
    *,
    user_instruction: str,
    prompt_set: dict[str, str],
    mode: str,
) -> str:
    if mode == "planner":
        return "\n\n".join(
            [
                "You are Dynamic Prompt Generator for the Planner V3 stage of an A2V pipeline.",
                "Your job is to adapt planner_sp.md and planner_os.md to the user's instruction while preserving the planner JSON contract.",
                "The user instruction has highest priority. If it conflicts with existing prompts, rewrite the planner prompts so the user instruction wins.",
                "Keep the planner focused on media-to-transcript matching. Do not add renderer layout rules to the planner.",
                "Do not remove required JSON validity rules. Do not invent unavailable media ids. Do not make the prompt less strict about valid JSON.",
                "Return valid JSON only. No markdown.",
                "Output schema:",
                '{"planner_sp":"...","planner_os":"...","change_summary":["short note"]}',
                "USER INSTRUCTION:",
                user_instruction,
                "CURRENT planner_sp.md:",
                prompt_set["planner_sp"],
                "CURRENT planner_os.md:",
                prompt_set["planner_os"],
            ]
        )
    if mode == "refiner":
        return "\n\n".join(
            [
                "You are Dynamic Prompt Generator for the Refiner V3 stage of an A2V pipeline.",
                "Your job is to adapt refiner_sp.md and refiner_os.md to the user's instruction while preserving the refiner JSON contract.",
                "The user instruction has highest priority. If it conflicts with existing prompts, rewrite the refiner prompts so the user instruction wins.",
                "Keep renderer compatibility: refiner output must remain valid JSON with background_timeline, caption_timeline, visual_timeline, warnings, and preset fields when useful.",
                "Examples: if the user says no captions, update refiner prompts/schema to avoid caption_timeline; if the user asks for a specific style, encode it explicitly.",
                "Do not remove required JSON validity rules. Do not create placeholder visual items. Do not make the prompt less strict about valid JSON.",
                "Return valid JSON only. No markdown.",
                "Output schema:",
                '{"refiner_sp":"...","refiner_os":"...","change_summary":["short note"]}',
                "USER INSTRUCTION:",
                user_instruction,
                "CURRENT refiner_sp.md:",
                prompt_set["refiner_sp"],
                "CURRENT refiner_os.md:",
                prompt_set["refiner_os"],
            ]
        )
    raise ValueError(f"unknown dynamic prompt mode: {mode}")


def _fallback_all(out_dir: Path, static_prompts: dict[str, str], report: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    write_json(out_dir / "dynamic_prompt_generator_report.json", report)
    for key, value in static_prompts.items():
        write_text(out_dir / f"{key}.fallback.md", value)
    return static_prompts, report


def _call_dynamic_prompt_half(
    *,
    base_planner_endpoint: str,
    user_instruction: str,
    static_prompts: dict[str, str],
    out_dir: Path,
    mode: str,
    keys: tuple[str, ...],
    max_tokens: int,
) -> tuple[dict[str, str] | None, dict[str, Any]]:
    request = _build_dynamic_prompt_request(user_instruction=user_instruction, prompt_set=static_prompts, mode=mode)
    write_text(out_dir / f"dynamic_prompt_generator_{mode}_request.txt", request)
    half_report: dict[str, Any] = {
        "mode": mode,
        "used_dynamic_prompts": False,
        "fallback_used": True,
        "warnings": [],
        "change_summary": [],
    }
    try:
        raw = call_llm_endpoint(base_planner_endpoint, request, temperature=0.0, max_tokens=max_tokens)
    except Exception as exc:
        half_report["warnings"].append(f"{mode}_dynamic_prompt_generation_failed:{exc}")
        write_text(out_dir / f"dynamic_prompt_generator_{mode}_response.txt", f"ERROR: {exc}")
        return None, half_report

    write_text(out_dir / f"dynamic_prompt_generator_{mode}_response.txt", raw)
    obj = parse_jsonish(raw)
    if not isinstance(obj, dict):
        half_report["warnings"].append(f"{mode}_dynamic_prompt_response_invalid_json")
        return None, half_report

    dynamic_prompts: dict[str, str] = {}
    for key in keys:
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            half_report["warnings"].append(f"{mode}_dynamic_prompt_missing_or_empty:{key}")
            return None, half_report
        dynamic_prompts[key] = value.strip()

    summary = obj.get("change_summary")
    if isinstance(summary, list):
        half_report["change_summary"] = [str(x) for x in summary]
    half_report["used_dynamic_prompts"] = True
    half_report["fallback_used"] = False
    write_json(out_dir / f"dynamic_prompt_generator_{mode}_output.json", {**dynamic_prompts, "change_summary": half_report["change_summary"]})
    return dynamic_prompts, half_report


def _build_legacy_dynamic_prompt_request(
    *,
    user_instruction: str,
    prompt_set: dict[str, str],
) -> str:
    return "\n\n".join(
        [
            "You are Dynamic Prompt Generator for an A2V planner/refiner pipeline.",
            "Your job is to adapt four prompt files to the user's instruction while preserving the pipeline JSON contracts.",
            "The user instruction has highest priority. If it conflicts with existing prompts, rewrite the prompts so the user instruction wins.",
            "Examples: if the user says no captions, update planner/refiner prompts and schemas to avoid caption rendering; if the user asks for documentary style, emphasize that style; if the user asks for revisions, encode them explicitly.",
            "Do not remove required JSON validity rules. Do not invent unavailable media ids. Do not make the prompt less strict about valid JSON.",
            "Keep the same four output keys exactly: planner_sp, planner_os, refiner_sp, refiner_os.",
            "Return valid JSON only. No markdown.",
            "Output schema:",
            '{"planner_sp":"...","planner_os":"...","refiner_sp":"...","refiner_os":"...","change_summary":["short note"]}',
            "USER INSTRUCTION:",
            user_instruction,
            "CURRENT planner_sp.md:",
            prompt_set["planner_sp"],
            "CURRENT planner_os.md:",
            prompt_set["planner_os"],
            "CURRENT refiner_sp.md:",
            prompt_set["refiner_sp"],
            "CURRENT refiner_os.md:",
            prompt_set["refiner_os"],
        ]
    )


def generate_dynamic_prompt_set(
    *,
    base_planner_endpoint: str | None,
    user_instruction: str,
    prompt_dir: str | Path,
    output_dir: str | Path,
    max_tokens: int = 7000,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Return dynamic prompts if generation succeeds, otherwise static prompts.

    Generated prompt files are intentionally written only into output_dir. The
    source prompt files in the repo remain unchanged and are always the fallback.
    """

    static_prompts = load_prompt_set(prompt_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "enabled": True,
        "used_dynamic_prompts": False,
        "fallback_used": True,
        "warnings": [],
        "change_summary": [],
        "planner": {},
        "refiner": {},
    }
    if not base_planner_endpoint:
        report["warnings"].append("base_planner_endpoint_missing")
        return _fallback_all(out_dir, static_prompts, report)

    prompt_set = dict(static_prompts)
    planner_prompts, planner_report = _call_dynamic_prompt_half(
        base_planner_endpoint=base_planner_endpoint,
        user_instruction=user_instruction,
        static_prompts=static_prompts,
        out_dir=out_dir,
        mode="planner",
        keys=PLANNER_PROMPT_KEYS,
        max_tokens=max_tokens,
    )
    refiner_prompts, refiner_report = _call_dynamic_prompt_half(
        base_planner_endpoint=base_planner_endpoint,
        user_instruction=user_instruction,
        static_prompts=static_prompts,
        out_dir=out_dir,
        mode="refiner",
        keys=REFINER_PROMPT_KEYS,
        max_tokens=max_tokens,
    )
    report["planner"] = planner_report
    report["refiner"] = refiner_report
    report["warnings"].extend(planner_report.get("warnings") or [])
    report["warnings"].extend(refiner_report.get("warnings") or [])

    if planner_prompts:
        prompt_set.update(planner_prompts)
    if refiner_prompts:
        prompt_set.update(refiner_prompts)

    for key in PROMPT_KEYS:
        value = prompt_set[key]
        if value != static_prompts[key]:
            write_text(out_dir / f"{key}.dynamic.md", value)
        write_text(out_dir / f"{key}.fallback.md", static_prompts[key])
    report["change_summary"] = list(planner_report.get("change_summary") or []) + list(refiner_report.get("change_summary") or [])
    report["used_dynamic_prompts"] = bool(planner_prompts or refiner_prompts)
    report["fallback_used"] = not report["used_dynamic_prompts"]
    report["fallback_used_for"] = [
        mode
        for mode, half in (("planner", planner_prompts), ("refiner", refiner_prompts))
        if not half
    ]
    write_json(out_dir / "dynamic_prompt_generator_report.json", report)
    write_json(out_dir / "dynamic_prompt_generator_output.json", {**prompt_set, "change_summary": report["change_summary"]})
    return prompt_set, report
