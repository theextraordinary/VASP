from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vasp.a2v.v3.schemas import GeneratedSegment, SegmentMedia
from vasp.a2v.v3.utils import (
    extract_caption_groups,
    extract_transcript,
    extract_word_map,
    json_md,
    media_by_id,
    media_probe,
    media_type,
    normalize_text,
    parse_jsonish_file,
)


def _find_timing_from_caption_groups(text: str, groups: list[dict[str, Any]]) -> tuple[float, float, list[dict[str, Any]]] | None:
    needle = normalize_text(text)
    if not needle:
        return None
    needle_words = needle.split()
    best: tuple[float, float, list[dict[str, Any]], float] | None = None
    exact_hits: list[tuple[int, int, list[dict[str, Any]]]] = []
    for i in range(len(groups)):
        combined = ""
        selected: list[dict[str, Any]] = []
        for j in range(i, len(groups)):
            selected.append(groups[j])
            combined = normalize_text(" ".join(str(g.get("text", "")) for g in selected))
            if combined == needle or needle in combined:
                exact_hits.append((i, j, list(selected)))
                break
            combined_words = combined.split()
            if combined_words and needle_words:
                common_prefix = 0
                for a, b in zip(combined_words, needle_words):
                    if a != b:
                        break
                    common_prefix += 1
                coverage = common_prefix / max(1, len(needle_words))
                if common_prefix == len(combined_words) and coverage >= 0.65:
                    best = (float(selected[0]["start"]), float(selected[-1]["end"]), list(selected), coverage)
                if common_prefix < len(combined_words) and common_prefix > 0:
                    break
            if len(combined) > len(needle) + 80:
                break
    if exact_hits:
        # Pick the tightest caption-group range. This avoids pulling in earlier
        # groups just because a later combined sentence contains the match text.
        _i, _j, selected = min(
            exact_hits,
            key=lambda row: (
                row[1] - row[0],
                len(normalize_text(" ".join(str(g.get("text", "")) for g in row[2]))),
                row[0],
            ),
        )
        return float(selected[0]["start"]), float(selected[-1]["end"]), selected
    if best:
        return best[0], best[1], best[2]
    return None


def _find_timing_from_words(text: str, words: list[dict[str, Any]]) -> tuple[float, float] | None:
    needle_words = normalize_text(text).split()
    if not needle_words:
        return None
    hay = [normalize_text(str(w.get("text", ""))) for w in words]
    n = len(needle_words)
    for i in range(0, max(0, len(hay) - n + 1)):
        if hay[i : i + n] == needle_words:
            return float(words[i]["start"]), float(words[i + n - 1]["end"])
    # Loose contiguous fallback.
    needle = " ".join(needle_words)
    for i in range(len(hay)):
        phrase = ""
        for j in range(i, min(len(hay), i + n + 5)):
            phrase = normalize_text((phrase + " " + hay[j]).strip())
            if needle in phrase or phrase in needle:
                return float(words[i]["start"]), float(words[j]["end"])
    return None


def _media_payload(media_id: str, media_json: dict[str, Any]) -> SegmentMedia:
    by_id = media_by_id(media_json)
    probe = media_probe(media_json)
    row = by_id.get(media_id, {})
    p = probe.get(media_id, {}) if isinstance(probe, dict) else {}
    return SegmentMedia(
        element_id=media_id,
        type=media_type(row),
        source_path=str(row.get("path") or ""),
        about=str(row.get("about") or ""),
        aim=str(row.get("aim") or ""),
        width=p.get("width") if isinstance(p, dict) else None,
        height=p.get("height") if isinstance(p, dict) else None,
        duration=p.get("duration") if isinstance(p, dict) else None,
    )


def _group_index(group: dict[str, Any], fallback: int) -> int:
    try:
        return int(group.get("index"))
    except Exception:
        return fallback


def _caption_only_segments(
    groups: list[dict[str, Any]],
    covered_indices: set[int],
) -> list[GeneratedSegment]:
    segments: list[GeneratedSegment] = []
    current: list[dict[str, Any]] = []
    max_groups_per_segment = 1

    def flush() -> None:
        if not current:
            return
        text = " ".join(str(g.get("text", "")).strip() for g in current if str(g.get("text", "")).strip()).strip()
        if not text:
            current.clear()
            return
        segments.append(
            GeneratedSegment(
                segment_id="",
                matched_text=text,
                t_start=round(float(current[0].get("start", 0.0) or 0.0), 3),
                t_end=round(float(current[-1].get("end", 0.0) or 0.0), 3),
                media_id="",
                media=SegmentMedia(element_id="", type="", source_path="", about="", aim=""),
                caption_groups=list(current),
                warnings=["caption_only_unmatched_from_media_json"],
            )
        )
        current.clear()

    for fallback, group in enumerate(groups):
        idx = _group_index(group, fallback)
        if idx in covered_indices:
            flush()
            continue
        current.append(group)
        if len(current) >= max_groups_per_segment:
            flush()
    flush()
    return segments


def generate_segments_from_planner_matches(
    planner_output_path: str | Path,
    media_json_path: str | Path,
    output_segments_dir: str | Path,
) -> list[Path]:
    planner = parse_jsonish_file(planner_output_path) or {"matches": [], "warnings": ["invalid planner json"]}
    media_json = json.loads(Path(media_json_path).read_text(encoding="utf-8"))
    groups = extract_caption_groups(media_json)
    words = extract_word_map(media_json)
    transcript = extract_transcript(media_json)
    duration = max([float(g["end"]) for g in groups], default=0.0)

    out_dir = Path(output_segments_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old_segment in out_dir.glob("segment_*.md"):
        if old_segment.is_file():
            old_segment.unlink()

    segments: list[GeneratedSegment] = []
    covered_caption_indices: set[int] = set()
    for idx, match in enumerate(planner.get("matches", []) if isinstance(planner.get("matches"), list) else [], start=1):
        if not isinstance(match, dict):
            continue
        text = str(match.get("text", "")).strip()
        media_id = str(match.get("media_id", "")).strip()
        warnings: list[str] = []
        if not text or not media_id:
            continue
        if normalize_text(text) not in normalize_text(transcript):
            warnings.append("match_text_not_found_in_full_transcript")

        caption_hit = _find_timing_from_caption_groups(text, groups)
        selected_groups: list[dict[str, Any]] = []
        if caption_hit:
            t_start, t_end, selected_groups = caption_hit
        else:
            word_hit = _find_timing_from_words(text, words)
            if not word_hit:
                continue
            t_start, t_end = word_hit
            selected_groups = [
                g for g in groups if float(g["end"]) > t_start and float(g["start"]) < t_end
            ]
            warnings.append("timing_found_from_word_map")

        match_word_count = len(normalize_text(text).split())
        transcript_word_count = len(normalize_text(transcript).split())
        if (
            selected_groups
            and transcript_word_count > 0
            and match_word_count >= max(40, int(transcript_word_count * 0.65))
            and len(selected_groups) >= 6
        ):
            # A broad whole-transcript planner match makes one media/image hold
            # for most of the video. Skip it so normal caption-only segments can
            # preserve the original timing instead of freezing the edit.
            continue

        if duration > 0:
            t_start = max(0.0, min(duration, t_start))
            t_end = max(0.0, min(duration, t_end))
        if t_end <= t_start:
            continue

        for fallback, group in enumerate(selected_groups):
            covered_caption_indices.add(_group_index(group, fallback))

        segments.append(
            GeneratedSegment(
                segment_id=f"segment_{len(segments) + 1:03d}",
                matched_text=text,
                t_start=round(t_start, 3),
                t_end=round(t_end, 3),
                media_id=media_id,
                media=_media_payload(media_id, media_json),
                caption_groups=selected_groups,
                warnings=warnings,
            )
        )

    segments.extend(_caption_only_segments(groups, covered_caption_indices))
    segments.sort(key=lambda s: (s.t_start, s.t_end))
    paths: list[Path] = []
    for i, seg in enumerate(segments, start=1):
        obj = seg.model_dump()
        obj["segment_id"] = f"segment_{i:03d}"
        p = out_dir / f"segment_{i:03d}.md"
        p.write_text(json_md(f"Segment {i:03d}", obj), encoding="utf-8")
        paths.append(p)
    return paths
