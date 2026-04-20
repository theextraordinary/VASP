from __future__ import annotations

from copy import deepcopy
from typing import Any


def caption_grouping(
    element_json: dict[str, Any],
    *,
    words_per_group: int = 3,
    pause_hold_threshold_s: float = 0.18,
    pause_split_threshold_s: float = 0.35,
) -> dict[str, Any]:
    """Group ASR word-caption elements into multi-word caption elements.

    - Only groups ASR word captions (`asr_caption_*` or metadata.source=asr_whisperx)
    - Group timing: first word start -> last word end
    - If gap between groups is small, extends previous group until next group starts
    """
    n = max(1, int(words_per_group))
    grouped_payload = deepcopy(element_json)
    elements = grouped_payload.get("elements", [])
    if not isinstance(elements, list) or not elements:
        return grouped_payload

    word_elements: list[dict[str, Any]] = []
    non_word_elements: list[dict[str, Any]] = []

    for row in elements:
        if _is_asr_word_caption(row):
            word_elements.append(row)
        else:
            non_word_elements.append(row)

    if len(word_elements) <= 1 or n <= 1:
        return grouped_payload

    word_elements.sort(key=lambda r: float((r.get("timing") or {}).get("start", 0.0)))

    grouped_chunks: list[list[dict[str, Any]]] = []
    current_chunk: list[dict[str, Any]] = []
    for row in word_elements:
        if not current_chunk:
            current_chunk.append(row)
            continue
        prev = current_chunk[-1]
        prev_end = float((prev.get("actions") or [{}])[0].get("t_end", (prev.get("timing") or {}).get("start", 0.0)))
        cur_start = float((row.get("actions") or [{}])[0].get("t_start", (row.get("timing") or {}).get("start", 0.0)))
        gap = cur_start - prev_end
        prev_word = _extract_caption_word(prev)
        cur_word = _extract_caption_word(row)

        should_split = (
            len(current_chunk) >= n
            or gap > float(pause_split_threshold_s)
            or _ends_sentence(prev_word)
            or _starts_with_upper(cur_word)
        )
        if should_split:
            grouped_chunks.append(current_chunk)
            current_chunk = [row]
        else:
            current_chunk.append(row)
    if current_chunk:
        grouped_chunks.append(current_chunk)

    groups: list[dict[str, Any]] = []
    for idx, chunk in enumerate(grouped_chunks):
        groups.append(_build_group_row(chunk, group_index=idx))

    # If silence/pause is very small, keep previous group visible until next starts.
    for i in range(len(groups) - 1):
        prev = groups[i]
        nxt = groups[i + 1]
        prev_action = (prev.get("actions") or [{}])[0]
        next_action = (nxt.get("actions") or [{}])[0]
        prev_end = float(prev_action.get("t_end", 0.0))
        next_start = float(next_action.get("t_start", 0.0))
        gap = next_start - prev_end
        if 0.0 < gap <= float(pause_hold_threshold_s):
            prev_action["t_end"] = next_start
            timing = prev.get("timing", {})
            start = float(timing.get("start", prev_action.get("t_start", 0.0)))
            timing["duration"] = max(0.0, next_start - start)
            prev["timing"] = timing
            props = prev.get("properties", {})
            if isinstance(props, dict):
                p_t = props.get("timing", {})
                if isinstance(p_t, dict):
                    p_t["duration"] = max(0.0, next_start - start)
                    props["timing"] = p_t
                    prev["properties"] = props

    grouped_payload["elements"] = non_word_elements + groups
    grouped_payload["elements"].sort(key=lambda r: float((r.get("timing") or {}).get("start", 0.0)))
    return grouped_payload


def _extract_caption_word(row: dict[str, Any]) -> str:
    props = row.get("properties", {})
    if isinstance(props, dict):
        text = str(props.get("text", "")).strip()
        if text:
            return text
    params = (row.get("actions") or [{}])[0].get("params", {})
    if isinstance(params, dict):
        return str(params.get("text", "")).strip()
    return ""


def _ends_sentence(text: str) -> bool:
    t = text.strip()
    return bool(t) and t[-1] in ".!?"


def _starts_with_upper(text: str) -> bool:
    t = text.lstrip()
    if not t:
        return False
    first = t[0]
    return first.isalpha() and first.isupper()


def _is_asr_word_caption(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    row_type = row.get("type")
    props = row.get("properties", {})
    props_type = props.get("type") if isinstance(props, dict) else None
    if row_type != "caption" and props_type != "caption":
        return False
    eid = str(row.get("element_id", ""))
    if eid.startswith("asr_caption_"):
        return True
    if isinstance(props, dict):
        meta = props.get("metadata", {})
        if isinstance(meta, dict):
            if bool(meta.get("grouped")):
                return False
            return str(meta.get("source", "")).lower() == "asr_whisperx"
    return False


def _build_group_row(chunk: list[dict[str, Any]], *, group_index: int) -> dict[str, Any]:
    first = deepcopy(chunk[0])
    last = chunk[-1]
    first_action = (first.get("actions") or [{}])[0]
    last_action = (last.get("actions") or [{}])[0]

    t_start = float(first_action.get("t_start", (first.get("timing") or {}).get("start", 0.0)))
    t_end = float(last_action.get("t_end", t_start))
    if t_end < t_start:
        t_end = t_start

    words: list[str] = []
    source_ids: list[str] = []
    for row in chunk:
        source_ids.append(str(row.get("element_id", "")))
        props = row.get("properties", {})
        text = ""
        if isinstance(props, dict):
            text = str(props.get("text", "")).strip()
        if text:
            words.append(text)

    grouped_text = " ".join(words).strip()
    group_id = f"asr_caption_group_{group_index}"

    first["element_id"] = group_id
    first["timing"] = {"start": t_start, "duration": max(0.0, t_end - t_start)}
    first["actions"] = [
        {
            "t_start": t_start,
            "t_end": t_end,
            "op": "show",
            "params": deepcopy(first_action.get("params", {})),
        }
    ]

    props = first.get("properties", {})
    if not isinstance(props, dict):
        props = {}
    props["text"] = grouped_text
    p_timing = props.get("timing", {})
    if not isinstance(p_timing, dict):
        p_timing = {}
    p_timing["start"] = t_start
    p_timing["duration"] = max(0.0, t_end - t_start)
    props["timing"] = p_timing

    meta = props.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}
    meta["grouped"] = True
    meta["group_word_count"] = len(chunk)
    meta["grouped_from_ids"] = source_ids
    meta["grouped_words"] = words
    props["metadata"] = meta

    first["properties"] = props
    first["type"] = "caption"
    return first
