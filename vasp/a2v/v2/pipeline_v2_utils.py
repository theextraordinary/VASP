from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def to_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def load_media_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_media_inventory(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    out: list[dict[str, Any]] = []
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    for row in inputs:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id", "")).strip()
        if not eid:
            continue
        p = probe.get(eid, {}) if isinstance(probe, dict) else {}
        out.append(
            {
                "element_id": eid,
                "type": str(row.get("media_type", "")).strip().lower(),
                "path": str(row.get("path", "")).strip(),
                "aim": str(row.get("aim", "")).strip(),
                "about": str(row.get("about", "")).strip(),
                "duration": to_float(p.get("duration"), 0.0),
                "width": p.get("width"),
                "height": p.get("height"),
            }
        )
    return out


def extract_main_audio_id(media_json: dict[str, Any]) -> str | None:
    for item in extract_media_inventory(media_json):
        t = item.get("type", "")
        if "audio" in t or t in {"music", "sfx"}:
            return str(item["element_id"])
    return None


def extract_audio_duration(media_json: dict[str, Any], main_audio_id: str | None) -> float:
    if not main_audio_id:
        return 0.0
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    if isinstance(probe, dict):
        return round(to_float((probe.get(main_audio_id) or {}).get("duration"), 0.0), 3)
    return 0.0


def extract_grouped_caption_map(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return []
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        groups = transcript.get("caption_groups")
        if not isinstance(groups, list):
            continue
        out: list[dict[str, Any]] = []
        for i, row in enumerate(groups):
            if not isinstance(row, dict):
                continue
            s = to_float(row.get("start"), -1.0)
            e = to_float(row.get("end"), -1.0)
            text = str(row.get("text", "")).strip()
            if s < 0 or e <= s or not text:
                continue
            out.append({"index": i, "start": round(s, 3), "end": round(e, 3), "text": text})
        if out:
            return out
    return []


def extract_main_transcript(media_json: dict[str, Any]) -> str:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return ""
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        full = str(transcript.get("full_text", "")).strip()
        if full:
            return full
    groups = extract_grouped_caption_map(media_json)
    return " ".join(g.get("text", "") for g in groups).strip()


def extract_whisper_segments(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    media_ctx = media_json.get("media_context") if isinstance(media_json, dict) else {}
    if not isinstance(media_ctx, dict):
        return []

    segs = media_ctx.get("segments")
    if isinstance(segs, list) and segs:
        return _normalize_segments(segs)

    analysis = media_ctx.get("analysis")
    if isinstance(analysis, dict):
        for block in analysis.values():
            if not isinstance(block, dict):
                continue
            transcript = block.get("transcript")
            if not isinstance(transcript, dict):
                continue
            s2 = transcript.get("segments")
            if isinstance(s2, list) and s2:
                return _normalize_segments(s2)

    return []


def _normalize_segments(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(raw):
        if not isinstance(seg, dict):
            continue
        s = to_float(seg.get("start", seg.get("t_start")), -1.0)
        e = to_float(seg.get("end", seg.get("t_end")), -1.0)
        if s < 0 or e <= s:
            continue
        text = str(seg.get("text", seg.get("spoken_text", ""))).strip()
        out.append(
            {
                "segment_id": str(seg.get("segment_id") or f"segment_{i:03d}"),
                "t_start": round(s, 3),
                "t_end": round(e, 3),
                "spoken_text": text,
            }
        )
    out.sort(key=lambda x: (x["t_start"], x["t_end"]))
    return out


def fallback_segments_from_caption_groups(
    grouped: list[dict[str, Any]],
    *,
    max_groups_per_segment: int = 4,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not grouped:
        return out
    bucket: list[dict[str, Any]] = []
    sid = 0
    for g in grouped:
        bucket.append(g)
        if len(bucket) >= max_groups_per_segment:
            out.append(_bucket_to_segment(bucket, sid))
            sid += 1
            bucket = []
    if bucket:
        out.append(_bucket_to_segment(bucket, sid))
    return out


def _bucket_to_segment(bucket: list[dict[str, Any]], sid: int) -> dict[str, Any]:
    return {
        "segment_id": f"segment_{sid:03d}",
        "t_start": round(to_float(bucket[0].get("start"), 0.0), 3),
        "t_end": round(to_float(bucket[-1].get("end"), 0.0), 3),
        "spoken_text": " ".join(str(x.get("text", "")).strip() for x in bucket).strip(),
    }


def caption_groups_for_segment(
    grouped: list[dict[str, Any]],
    segment: dict[str, Any],
) -> list[dict[str, Any]]:
    s = to_float(segment.get("t_start"), 0.0)
    e = to_float(segment.get("t_end"), s)
    out: list[dict[str, Any]] = []
    for g in grouped:
        gs = to_float(g.get("start"), -1.0)
        ge = to_float(g.get("end"), -1.0)
        if gs < 0 or ge <= gs:
            continue
        if ge > s and gs < e:
            out.append(g)
    out.sort(key=lambda x: (to_float(x.get("start"), 0.0), to_float(x.get("end"), 0.0)))
    return out


def caption_boundary_set(groups: list[dict[str, Any]]) -> set[float]:
    out: set[float] = set()
    for g in groups:
        out.add(round(to_float(g.get("start"), 0.0), 3))
        out.add(round(to_float(g.get("end"), 0.0), 3))
    return out

