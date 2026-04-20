from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROLE_VALUES = {"high", "medium", "low"}
MATCH_STYLE_VALUES = {"literal", "emotional", "humorous", "contextual", "reaction", "cinematic", "transition", "fallback"}
EMOTIONAL_STYLES = {"emotional", "humorous", "reaction"}
FILLER_SPANS = {
    "today was the day",
    "the story moved forward",
    "for many viewers",
    "at first glance",
    "the context was easy to miss",
    "what happened next",
    "by the end of the day",
    "the detail mattered",
    "this was not obvious",
    "a small clue appeared",
    "coming to 1807",
}
VAGUE_SPANS = {"are known", "is known", "was known", "were known", "to see", "as the", "in the", "of the"}


def _section(text: str, name: str, next_names: tuple[str, ...]) -> str:
    start = text.find(name + ":")
    if start < 0:
        return ""
    start += len(name) + 1
    end = len(text)
    for n in next_names:
        pos = text.find("\n" + n + ":", start)
        if pos >= 0:
            end = min(end, pos)
    return text[start:end].strip()


def _parse_media_ids(block: str) -> set[str]:
    ids: set[str] = set()
    for line in block.splitlines():
        m = re.match(r"\s*(media_\d+)\s*\|", line)
        if m:
            ids.add(m.group(1))
    return ids


def _find_spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            break
        spans.append((i, i + len(needle)))
        start = i + 1
    return spans


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _parse_prompt(input_text: str) -> tuple[str, set[str], set[str]]:
    transcript = _section(input_text, "FULL TRANSCRIPT", ("MANDATORY MEDIA", "OPTIONAL MEDIA", "Planner output schema"))
    mandatory = _parse_media_ids(_section(input_text, "MANDATORY MEDIA", ("OPTIONAL MEDIA", "Planner output schema")))
    optional = _parse_media_ids(_section(input_text, "OPTIONAL MEDIA", ("Planner output schema", "Validation")))
    return transcript, mandatory, optional


def _is_date_only_or_filler(text: str) -> bool:
    norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()
    if norm in FILLER_SPANS or norm in VAGUE_SPANS:
        return True
    if re.fullmatch(r"(in|by|around|during)?\s*\d{3,4}", norm):
        return True
    words = norm.split()
    if len(words) <= 2 and any(w.isdigit() for w in words):
        return True
    if words and words[0] in {"coming", "today", "then", "next"} and len(words) <= 4:
        return True
    return False


def validate_planner_v3_example(input_text: str, output_json: str | dict[str, Any]) -> list[str]:
    errors: list[str] = []
    transcript, mandatory_ids, optional_ids = _parse_prompt(input_text)
    all_ids = mandatory_ids | optional_ids
    if not transcript:
        errors.append("missing FULL TRANSCRIPT")
    if not mandatory_ids:
        errors.append("missing mandatory media ids")

    if isinstance(output_json, str):
        if "```" in output_json:
            errors.append("assistant output contains markdown")
        try:
            output = json.loads(output_json)
        except Exception as exc:
            return errors + [f"assistant output is not complete JSON: {exc}"]
    else:
        output = output_json

    if not isinstance(output, dict):
        return errors + ["assistant output must be object"]
    if output.get("planner_version") != "v3_media_text_matching":
        errors.append("planner_version mismatch")
    matches = output.get("matches")
    unmatched = output.get("unmatched_text")
    warnings = output.get("warnings")
    if not isinstance(matches, list):
        errors.append("matches must be list")
        matches = []
    if not isinstance(unmatched, list):
        errors.append("unmatched_text must be list")
        unmatched = []
    if not isinstance(warnings, list):
        errors.append("warnings must be list")

    used_mandatory: set[str] = set()
    match_spans: list[tuple[int, int, str]] = []
    for idx, match in enumerate(matches, start=1):
        if not isinstance(match, dict):
            errors.append(f"match {idx} must be object")
            continue
        expected_id = f"match_{idx:03d}"
        if match.get("match_id") != expected_id:
            errors.append(f"match_id sequence error: expected {expected_id}")
        text = str(match.get("text", ""))
        media_id = str(match.get("media_id", ""))
        if media_id not in all_ids:
            errors.append(f"unknown media_id: {media_id}")
        is_mandatory = media_id in mandatory_ids
        if bool(match.get("mandatory_media")) != is_mandatory:
            errors.append(f"mandatory_media boolean wrong for {media_id}")
        if is_mandatory:
            used_mandatory.add(media_id)
        if match.get("match_strength") not in ROLE_VALUES:
            errors.append(f"invalid match_strength for {media_id}")
        style = match.get("match_style")
        if style not in MATCH_STYLE_VALUES:
            errors.append(f"invalid match_style for {media_id}")
        if not isinstance(match.get("match_reason"), str):
            errors.append(f"match_reason must be string for {media_id}")
        if _is_date_only_or_filler(text):
            if match.get("match_strength") != "low" or style != "fallback":
                errors.append(f"weak/date/filler span must be low fallback: {text[:60]}")
        spans = _find_spans(transcript, text)
        if not spans:
            errors.append(f"match.text not exact transcript substring: {text[:60]}")
            continue
        span = spans[0]
        for old_start, old_end, old_text in match_spans:
            if _overlap(span, (old_start, old_end)):
                errors.append(f"matched spans overlap: {text[:40]} <> {old_text[:40]}")
        match_spans.append((span[0], span[1], text))

    missing = sorted(mandatory_ids - used_mandatory)
    if missing:
        errors.append("mandatory media not used: " + ", ".join(missing))

    for row in unmatched:
        if not isinstance(row, dict):
            errors.append("unmatched_text item must be object")
            continue
        text = str(row.get("text", ""))
        spans = _find_spans(transcript, text)
        if not spans:
            errors.append(f"unmatched text not exact transcript substring: {text[:60]}")
            continue
        span = spans[0]
        for ms, me, mt in match_spans:
            if _overlap(span, (ms, me)):
                errors.append(f"unmatched overlaps matched text: {text[:40]} <> {mt[:40]}")
        if not isinstance(row.get("reason"), str):
            errors.append("unmatched reason must be string")

    return errors


def validate_jsonl(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    rows = 0
    failures: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    style_counts: dict[str, int] = {}
    rows_with_emotional_style = 0
    total_matches = 0
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        rows += 1
        try:
            row = json.loads(line)
            messages = row["messages"]
            input_text = messages[0]["content"]
            output_text = messages[1]["content"]
        except Exception as exc:
            failures.append({"line": line_no, "errors": [f"row parse error: {exc}"]})
            continue
        errors = validate_planner_v3_example(input_text, output_text)
        try:
            output = json.loads(output_text)
            row_has_emotional = False
            for match in output.get("matches", []):
                if not isinstance(match, dict):
                    continue
                total_matches += 1
                reason = str(match.get("match_reason", ""))
                style = str(match.get("match_style", ""))
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                style_counts[style] = style_counts.get(style, 0) + 1
                if style in EMOTIONAL_STYLES:
                    row_has_emotional = True
            if row_has_emotional:
                rows_with_emotional_style += 1
        except Exception:
            pass
        if errors:
            failures.append({"line": line_no, "errors": errors})
    warnings: list[str] = []
    emotional_row_ratio = rows_with_emotional_style / rows if rows else 0.0
    emotional_match_ratio = sum(style_counts.get(s, 0) for s in EMOTIONAL_STYLES) / total_matches if total_matches else 0.0
    fallback_ratio = style_counts.get("fallback", 0) / total_matches if total_matches else 0.0
    repeated_reasons = {k: v for k, v in reason_counts.items() if total_matches and v / total_matches > 0.12}
    if emotional_row_ratio < 0.30 and emotional_match_ratio < 0.30:
        warnings.append(f"emotional/humorous/reaction styles below 30%: rows={emotional_row_ratio:.3f}, matches={emotional_match_ratio:.3f}")
    if fallback_ratio > 0.15:
        warnings.append(f"fallback style exceeds 15%: {fallback_ratio:.3f}")
    if repeated_reasons:
        warnings.append("match_reason repeats too much: " + ", ".join(f"{k}={v}" for k, v in sorted(repeated_reasons.items(), key=lambda kv: -kv[1])[:8]))
    return {
        "path": str(p),
        "rows": rows,
        "passed": rows - len(failures),
        "failed": len(failures),
        "failures": failures,
        "warnings": warnings,
        "style_counts": style_counts,
        "reason_top": sorted(reason_counts.items(), key=lambda kv: -kv[1])[:20],
        "emotional_row_ratio": round(emotional_row_ratio, 4),
        "emotional_match_ratio": round(emotional_match_ratio, 4),
        "fallback_ratio": round(fallback_ratio, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="vasp/a2v/finetuning/planner_v3_dataset/output/planner_v3_500_examples.jsonl")
    parser.add_argument("--report", default="vasp/a2v/finetuning/planner_v3_dataset/output/validation_report.json")
    args = parser.parse_args()
    report = validate_jsonl(args.input)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("rows", "passed", "failed")}, indent=2))
    return 0 if report["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
