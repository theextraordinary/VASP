from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

from vasp.a2v.v2.media_crawler import crawl_one_gif_one_image
from vasp.a2v.v3.utils import call_llm_endpoint, parse_jsonish, write_json, write_text


MODES = {"none", "library", "crawl", "generate"}
VISUAL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".ogv"}
CRAWLED_DATA_DIR = Path("assets/crawled_data")
LIBRARY_CHUNK_SIZE = 200
LIBRARY_MAX_CHUNKS = 10
OPTIONAL_MEDIA_MIN_COUNT = 5
OPTIONAL_MEDIA_MAX_COUNT = 50
STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "into",
    "when",
    "where",
    "what",
    "which",
    "then",
    "than",
    "they",
    "them",
    "their",
    "about",
    "after",
    "before",
    "during",
    "because",
    "through",
    "while",
    "today",
    "coming",
    "next",
    "just",
    "very",
    "really",
    "also",
    "like",
}


def _debug_root(edit_name: str, debug_dir: str | Path | None = None) -> Path:
    root = Path(debug_dir) if debug_dir else Path("output") / "edits" / edit_name / "optional_media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clamp_optional_media_count(count: int) -> int:
    try:
        value = int(count)
    except Exception:
        value = 10
    return max(OPTIONAL_MEDIA_MIN_COUNT, min(OPTIONAL_MEDIA_MAX_COUNT, value))


def _portable(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def _media_type_from_path(path: str | Path, declared: str = "") -> str:
    ext = Path(str(path)).suffix.lower()
    if ext == ".gif":
        return "gif"
    if ext in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".ogv"}:
        return "video"
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"
    d = declared.lower()
    if "gif" in d:
        return "gif"
    if "video" in d:
        return "video"
    return "image"


def _read_library_captions(asset_library_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(asset_library_dir)
    library_captions = root / "captions.txt"
    if not library_captions.exists():
        return []
    rows_by_path: dict[str, dict[str, Any]] = {}
    with library_captions.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            media_name = str(
                row.get("media_name")
                or row.get("filename")
                or row.get("file")
                or row.get("image")
                or row.get("img")
                or row.get("media")
                or ""
            ).strip()
            explicit_path = str(row.get("path") or row.get("source_path") or row.get("source_uri") or "").strip()
            about = str(row.get("about") or row.get("caption") or row.get("description") or "").strip()
            if not media_name and explicit_path:
                media_name = Path(explicit_path).name
            if not media_name or not about:
                continue
            path = Path(explicit_path) if explicit_path else root / media_name
            if not path.is_absolute() and explicit_path:
                path = root / explicit_path
            if path.suffix.lower() not in VISUAL_EXTENSIONS:
                continue
            key = str(path.resolve())
            if key in rows_by_path:
                captions = rows_by_path[key].setdefault("captions", [])
                if about and about not in captions:
                    captions.append(about)
                continue
            captions = [about] if about else []
            rows_by_path[key] = {
                    "media_name": media_name,
                    "path": _portable(path),
                    "about": about,
                    "captions": captions,
                    "aim": str(row.get("aim") or "show when relevant caption topic is spoken"),
                    "type": _media_type_from_path(path, str(row.get("type") or "")),
                    "source": "library",
                    "license": str(row.get("license") or ""),
                    "path_exists": path.exists(),
                }
    return list(rows_by_path.values())


def _keywords(text: str, limit: int = 24) -> list[str]:
    words = re.findall(r"[A-Z][a-zA-Z]{2,}|[a-zA-Z]{4,}", text or "")
    scored: dict[str, int] = {}
    for w in words:
        key = w.lower()
        if key in STOPWORDS:
            continue
        scored[key] = scored.get(key, 0) + (3 if w[:1].isupper() else 1)
    return [w for w, _score in sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _proper_name_queries(text: str, limit: int = 5) -> list[str]:
    # Deterministic safety net for famous-person/name queries. The base planner
    # may miss names; multi-token Title Case spans are usually the best local
    # signal without adding a heavy NER dependency.
    blocked_starts = {
        "Today",
        "Coming",
        "But",
        "Then",
        "Now",
        "This",
        "That",
        "When",
        "While",
        "Because",
        "After",
        "Before",
        "In",
        "On",
        "At",
        "The",
        "A",
        "An",
    }
    pattern = re.compile(r"\b(?:[A-Z][a-zA-Z.'-]{2,}\s+){1,4}[A-Z][a-zA-Z.'-]{2,}\b")
    seen: set[str] = set()
    out: list[str] = []
    for match in pattern.finditer(text or ""):
        name = re.sub(r"\s+", " ", match.group(0)).strip(" ,.;:!?")
        parts = name.split()
        if len(parts) < 2 or parts[0] in blocked_starts:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= limit:
            break
    return out


def _keyword_score(text: str, keywords: list[str]) -> int:
    hay = (text or "").lower()
    return sum(1 for kw in keywords if kw.lower() in hay)


def _rank_items(items: list[dict[str, Any]], transcript: str, limit: int) -> list[dict[str, Any]]:
    kws = _keywords(transcript)
    ranked = sorted(
        items,
        key=lambda row: (
            -_keyword_score(" ".join(str(row.get(k, "")) for k in ("media_name", "about", "aim")), kws),
            str(row.get("media_name") or row.get("path") or ""),
        ),
    )
    return ranked[: max(0, limit)]


def _call_base_planner(
    endpoint: str | None,
    prompt: str,
    debug_dir: Path,
    max_tokens: int = 1200,
    *,
    request_name: str = "base_planner_request.txt",
    response_name: str = "base_planner_response.txt",
) -> dict[str, Any] | None:
    request_path = write_text(debug_dir / request_name, prompt)
    print(f"[OPTIONAL_MEDIA] wrote base planner prompt: {request_path}")
    if not endpoint:
        response_path = write_text(debug_dir / response_name, "")
        print(f"[OPTIONAL_MEDIA] no base planner endpoint; wrote empty response: {response_path}")
        return None
    try:
        raw = call_llm_endpoint(endpoint, prompt, temperature=0.0, max_tokens=max_tokens)
    except Exception as exc:
        raw = f"ERROR: {exc}"
        response_path = write_text(debug_dir / response_name, raw)
        print(f"[OPTIONAL_MEDIA] base planner call failed; wrote response: {response_path}")
        return None
    response_path = write_text(debug_dir / response_name, raw)
    print(f"[OPTIONAL_MEDIA] wrote base planner response: {response_path}")
    return parse_jsonish(raw)


def _read_prompt_template(name: str, fallback: str) -> str:
    path = Path(__file__).resolve().parent / "prompts" / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else fallback.strip()


def _read_library_selection_sp() -> str:
    path = Path(__file__).resolve().parent / "v3" / "prompts" / "library_selection_sp.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return _read_prompt_template(
        "base_select_library_media.md",
        """
You are Library Media Selector for an A2V short-form video pipeline.
Return valid JSON only: {{"selected_media":[{{"media_name":"...","reason":"...","about":"..."}}]}}
Only select filenames that appear exactly in LIBRARY CAPTIONS.
""",
    )


def _format_library_list(rows: list[dict[str, Any]]) -> str:
    lines = []
    for row in rows:
        lines.append(f"{row['media_name']} | {row['type']} | about: {row['about']} | aim: {row['aim']}")
    return "\n".join(lines) or "(none)"


def _format_library_captions_csv(rows: list[dict[str, Any]]) -> str:
    lines = ["file,about"]
    for row in rows:
        media_name = str(row.get("media_name") or "").replace("\n", " ").strip()
        captions = row.get("captions") if isinstance(row.get("captions"), list) else []
        caption_text = " | ".join(str(c).strip() for c in captions[:5] if str(c).strip()) or str(row.get("about") or "")
        about = caption_text.replace("\n", " ").replace('"', "'").strip()
        lines.append(f"{media_name},{about}")
    return "\n".join(lines)


def _build_library_selection_prompt(
    *,
    system_prompt: str,
    transcript: str,
    user_instruction: str,
    media_library_csv: str,
    optional_media_count: int,
    chunk_idx: int,
    chunks_total: int,
) -> str:
    return "\n\n".join(
        [
            system_prompt,
            f"REQUESTED_SELECTION_COUNT_FOR_THIS_CHUNK:\n{optional_media_count}",
            f"CHUNK:\n{chunk_idx} of {chunks_total}",
            f"USER INSTRUCTION:\n{user_instruction}",
            f"TRANSCRIPT:\n{transcript}",
            "MEDIA LIBRARY:\n" + media_library_csv,
            "Return only the JSON object with selected_media.",
        ]
    )


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    size = max(1, int(size or LIBRARY_CHUNK_SIZE))
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _to_optional_rows(rows: list[dict[str, Any]], source: str, count: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[: max(0, count)], start=1):
        path = str(row.get("path") or "").strip()
        if not path or not Path(path).exists():
            print(f"[OPTIONAL_MEDIA] selected library media file missing, skipping insert: {path or row.get('media_name')}")
            continue
        out.append(
            {
                "element_id": f"optional_media_{idx}",
                "type": _media_type_from_path(path, str(row.get("type") or "")),
                "path": _portable(path),
                "about": str(row.get("about") or ""),
                "aim": str(row.get("aim") or "show when relevant caption topic is spoken"),
                "source_about": str(row.get("source_about") or ""),
                "source": source,
                "license": str(row.get("license") or ""),
                "selection_reason": str(row.get("selection_reason") or ""),
                "transcript_part": str(row.get("transcript_part") or ""),
                "width": None,
                "height": None,
                "duration": None,
            }
        )
    return out


def _select_library_media(
    transcript: str,
    user_instruction: str,
    base_planner_endpoint: str | None,
    asset_library_dir: str | Path,
    optional_media_count: int,
    debug_dir: Path,
) -> list[dict[str, Any]]:
    root = Path(asset_library_dir)
    library_captions_path = root / "captions.txt"
    library = _read_library_captions(asset_library_dir)
    if not library:
        prompt_path = write_text(
            debug_dir / "base_planner_prompt.txt",
            "\n\n".join(
                [
                    _read_library_selection_sp(),
                    f"USER INSTRUCTION:\n{user_instruction}",
                    f"TRANSCRIPT:\n{transcript}",
                    "MEDIA LIBRARY:\nfile,about",
                    "Return only the JSON object with selected_media.",
                ]
            ),
        )
        response_path = write_text(debug_dir / "base_planner_response.txt", "")
        print(f"[OPTIONAL_MEDIA] library mode found no usable media.")
        print(f"[OPTIONAL_MEDIA] optional library captions file: {library_captions_path}")
        print(f"[OPTIONAL_MEDIA] wrote diagnostic base planner prompt: {prompt_path}")
        print(f"[OPTIONAL_MEDIA] wrote diagnostic base planner response: {response_path}")
        write_json(
            debug_dir / "library_selection_summary.json",
            {
                "library_count": 0,
                "asset_library_dir": _portable(root),
                "asset_library_dir_exists": root.exists(),
                "library_captions_path": _portable(library_captions_path),
                "library_captions_exists": library_captions_path.exists(),
                "selected_media_names": [],
                "reason": "No usable library rows found. Ensure captions.txt exists and each row points to an existing visual file.",
            },
        )
        return []
    ranked_library = _rank_items(library, transcript, len(library))
    print(f"[OPTIONAL_MEDIA] optional library captions file: {library_captions_path}")
    print(f"[OPTIONAL_MEDIA] optional library rows loaded: {len(library)}")
    system_prompt = _read_library_selection_sp()
    by_name = {row["media_name"]: row for row in library}
    by_basename = {Path(row["media_name"]).name: row["media_name"] for row in library}
    selected_about_by_name: dict[str, str] = {}
    selected_aim_by_name: dict[str, str] = {}
    selected_reason_by_name: dict[str, str] = {}
    selected_transcript_part_by_name: dict[str, str] = {}
    candidate_names: list[str] = []
    chunk_debug_dir = debug_dir / "library_chunks"
    chunk_debug_dir.mkdir(parents=True, exist_ok=True)
    chunk_target = max(optional_media_count * 2, optional_media_count)
    chunks = _chunks(ranked_library, LIBRARY_CHUNK_SIZE)[:LIBRARY_MAX_CHUNKS]
    chunks_considered = 0
    prompts_used: list[str] = []
    for chunk_idx, chunk in enumerate(chunks, start=1):
        chunks_considered = chunk_idx
        prompt = _build_library_selection_prompt(
            system_prompt=system_prompt,
            transcript=transcript,
            user_instruction=user_instruction,
            media_library_csv=_format_library_captions_csv(chunk),
            optional_media_count=min(chunk_target, len(chunk)),
            chunk_idx=chunk_idx,
            chunks_total=len(chunks),
        )
        prompts_used.append(f"===== LIBRARY SELECTION CHUNK {chunk_idx:03d} OF {len(chunks):03d} =====\n\n{prompt}")
        obj = _call_base_planner(
            base_planner_endpoint,
            prompt,
            chunk_debug_dir,
            request_name=f"base_planner_prompt_chunk_{chunk_idx:03d}.txt",
            response_name=f"base_planner_response_chunk_{chunk_idx:03d}.txt",
        )
        if isinstance(obj, dict) and isinstance(obj.get("selected_media"), list):
            for item in obj["selected_media"]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("media_name") or item.get("file") or item.get("filename") or "").strip()
                if name not in by_name and Path(name).name in by_basename:
                    name = by_basename[Path(name).name]
                if name in by_name and name not in candidate_names:
                    candidate_names.append(name)
                    returned_about = str(item.get("about") or "").strip()
                    if returned_about:
                        selected_about_by_name[name] = returned_about
                    transcript_part = str(item.get("transcript_part") or item.get("text") or "").strip()
                    returned_aim = str(item.get("aim") or "").strip()
                    returned_reason = str(item.get("reason") or "").strip()
                    if transcript_part:
                        selected_transcript_part_by_name[name] = transcript_part
                    if returned_aim:
                        selected_aim_by_name[name] = returned_aim
                    elif transcript_part:
                        selected_aim_by_name[name] = f"show during '{transcript_part}'"
                    if returned_reason:
                        selected_reason_by_name[name] = returned_reason
        # Stop early only after scanning a healthy number of high-ranked chunks.
        if len(candidate_names) >= max(optional_media_count * 4, optional_media_count) and chunk_idx >= 3:
            break

    if prompts_used:
        aggregate_prompt_path = write_text(debug_dir / "base_planner_prompt.txt", "\n\n".join(prompts_used))
        print(f"[OPTIONAL_MEDIA] wrote aggregate base planner prompt: {aggregate_prompt_path}")

    response_parts: list[str] = []
    for response_path in sorted(chunk_debug_dir.glob("base_planner_response_chunk_*.txt")):
        response_parts.append(f"===== {response_path.name} =====\n\n{response_path.read_text(encoding='utf-8', errors='ignore')}")
    if response_parts:
        aggregate_response_path = write_text(debug_dir / "base_planner_response.txt", "\n\n".join(response_parts))
        print(f"[OPTIONAL_MEDIA] wrote aggregate base planner response: {aggregate_response_path}")

    candidates = [by_name[name] for name in candidate_names if name in by_name]
    for row in candidates:
        name = str(row.get("media_name") or "")
        if selected_about_by_name.get(name):
            row["about"] = selected_about_by_name[name]
        if selected_aim_by_name.get(name):
            row["aim"] = selected_aim_by_name[name]
        if selected_reason_by_name.get(name):
            row["selection_reason"] = selected_reason_by_name[name]
        if selected_transcript_part_by_name.get(name):
            row["transcript_part"] = selected_transcript_part_by_name[name]
    selected: list[dict[str, Any]] = _rank_items(candidates, transcript, optional_media_count) if candidates else []
    if len(selected) < optional_media_count:
        for row in ranked_library:
            if row not in selected:
                selected.append(row)
            if len(selected) >= optional_media_count:
                break
    write_json(
        debug_dir / "library_selection_summary.json",
        {
            "library_count": len(library),
            "library_files_available": sum(1 for row in library if row.get("path_exists")),
            "chunk_size": LIBRARY_CHUNK_SIZE,
            "max_chunks": LIBRARY_MAX_CHUNKS,
            "chunks_total": len(chunks),
            "chunks_considered": chunks_considered,
            "candidate_count": len(candidate_names),
            "selected_media_names": [row.get("media_name") for row in selected],
            "prompt_source": "vasp/a2v/v3/prompts/library_selection_sp.md",
        },
    )
    optional_rows = _to_optional_rows(selected, "library", optional_media_count)
    print(
        "[OPTIONAL_MEDIA] library selection summary: "
        f"loaded={len(library)} chunks_considered={chunks_considered} "
        f"candidates={len(candidate_names)} selected={len(optional_rows)}"
    )
    return optional_rows


def _fallback_queries(transcript: str, count: int) -> list[str]:
    kws = _keywords(transcript, limit=16)
    queries: list[str] = _proper_name_queries(transcript, limit=count)
    for i in range(0, len(kws), 2):
        query = " ".join(kws[i : i + 2])
        if query and query.lower() not in {q.lower() for q in queries}:
            queries.append(query)
        if len(queries) >= count:
            break
    return queries


def _write_crawled_data_captions(rows: list[dict[str, Any]], captions_path: Path) -> Path:
    captions_path.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, dict[str, str]] = {}
    if captions_path.exists():
        with captions_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            first_line = sample.splitlines()[0] if sample.splitlines() else ""
            delimiter = "\t" if "\t" in sample and "," not in first_line else ","
            for raw_old in csv.DictReader(f, delimiter=delimiter):
                old = {str(k or "").strip().lstrip("\ufeff"): v for k, v in raw_old.items()}
                file_name = str(old.get("file") or old.get("media_name") or "").strip()
                if not file_name:
                    continue
                merged[file_name] = {
                    "file": file_name,
                    "about": str(old.get("about") or "").strip(),
                    "aim": str(old.get("aim") or "").strip(),
                }
    with captions_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "about", "aim"])
        for row in rows:
            file_name = Path(str(row.get("path") or row.get("media_name") or row.get("file") or "")).name
            if not file_name:
                continue
            merged[file_name] = {
                "file": file_name,
                "about": str(row.get("crawl_query") or row.get("about") or "").strip(),
                "aim": str(row.get("aim") or row.get("selection_reason") or "").strip(),
            }
        for file_name in sorted(merged):
            row = merged[file_name]
            writer.writerow([row["file"], row["about"], row["aim"]])
    return captions_path


def _read_caption_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        delimiter = "\t" if "\t" in sample and "," not in first_line else ","
        rows: list[dict[str, str]] = []
        for raw_row in csv.DictReader(f, delimiter=delimiter):
            row = {str(k or "").strip().lstrip("\ufeff"): v for k, v in raw_row.items()}
            file_name = str(
                row.get("file")
                or row.get("media_name")
                or row.get("filename")
                or row.get("media")
                or ""
            ).strip()
            about = str(row.get("about") or row.get("caption") or row.get("description") or "").strip()
            aim = str(row.get("aim") or "").strip()
            if file_name and about:
                rows.append({"file": file_name, "about": about, "aim": aim})
        return rows


def _unique_library_path(path: Path) -> Path:
    if not path.exists():
        return path
    idx = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{idx}{path.suffix}")
        if not candidate.exists():
            return candidate
        idx += 1


def promote_crawled_data_to_library(
    crawled_data_dir: str | Path = CRAWLED_DATA_DIR,
    asset_library_dir: str | Path = "assets/library",
    debug_dir: str | Path | None = None,
) -> dict[str, Any]:
    crawl_root = Path(crawled_data_dir)
    library_root = Path(asset_library_dir)
    captions_path = crawl_root / "captions.txt"
    report: dict[str, Any] = {
        "crawled_data_dir": str(crawl_root).replace("\\", "/"),
        "asset_library_dir": str(library_root).replace("\\", "/"),
        "moved_files": [],
        "appended_rows": 0,
        "prepended_rows": 0,
        "warnings": [],
    }
    if not crawl_root.exists():
        report["warnings"].append("crawled_data_dir_missing")
        return report

    rows = _read_caption_rows(captions_path)
    rows_by_file = {row["file"]: row for row in rows}
    library_root.mkdir(parents=True, exist_ok=True)
    promoted_rows: list[dict[str, str]] = []

    for path in sorted(crawl_root.iterdir()):
        if not path.is_file() or path.name == "captions.txt":
            continue
        if path.suffix.lower() not in VISUAL_EXTENSIONS:
            report["warnings"].append(f"skipped_non_visual:{path.name}")
            continue
        target = _unique_library_path(library_root / path.name)
        shutil.move(str(path), str(target))
        row = dict(rows_by_file.get(path.name) or {})
        if not row:
            row = {
                "file": target.name,
                "about": path.stem.replace("_", " "),
                "aim": "show when relevant caption topic is spoken",
            }
        row["file"] = target.name
        promoted_rows.append(row)
        report["moved_files"].append({"from": path.name, "to": target.name})

    if promoted_rows:
        library_captions = library_root / "captions.txt"
        existing_rows = _read_caption_rows(library_captions)
        with library_captions.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["file", "about", "aim"])
            # Put freshly crawled media first so future library-mode selection
            # sees the most recent, topic-relevant assets before the large
            # generic library tail.
            for row in promoted_rows + existing_rows:
                writer.writerow([row.get("file", ""), row.get("about", ""), row.get("aim", "")])
        report["appended_rows"] = len(promoted_rows)
        report["prepended_rows"] = len(promoted_rows)

    for leftover in sorted(crawl_root.iterdir()):
        if leftover.is_file():
            leftover.unlink(missing_ok=True)
    if debug_dir:
        dbg = Path(debug_dir)
        dbg.mkdir(parents=True, exist_ok=True)
        write_json(dbg / "crawled_data_promotion_report.json", report)
    print(
        "[OPTIONAL_MEDIA] promoted crawled data to library: "
        f"moved={len(report['moved_files'])} prepended_rows={report['prepended_rows']}"
    )
    return report


def _collect_crawl_media(
    transcript: str,
    user_instruction: str,
    edit_name: str,
    base_planner_endpoint: str | None,
    collected_assets_dir: str | Path,
    optional_media_count: int,
    crawl_total_per_query: int,
    crawl_funny_percent: int,
    debug_dir: Path,
) -> list[dict[str, Any]]:
    template = _read_prompt_template(
        "base_generate_crawl_queries.md",
        """
Generate exactly {query_count} safe media search queries for this A2V transcript.
Return valid JSON only: {{"queries":[{{"query":"...","reason":"..."}}]}}
Queries must be short, diverse, and visual.
First identify any famous/known person names in the transcript.
If the transcript contains a famous/known person name, at least one query must be exactly that person's name or that person's name plus one visual keyword.
Then identify any animal, place, named object, invention, product, event, or particular thing in the transcript.
You must generate direct queries for those specific entities when they are safe and visually searchable.
TRANSCRIPT:
{transcript}
USER INSTRUCTION:
{user_instruction}
""",
    )
    query_count = max(1, int(optional_media_count or 1))
    prompt = template.format(
        transcript=transcript,
        user_instruction=user_instruction,
        edit_name=edit_name,
        query_count=query_count,
    )
    obj = _call_base_planner(base_planner_endpoint, prompt, debug_dir)
    query_items: list[dict[str, str]] = []
    if isinstance(obj, dict) and isinstance(obj.get("queries"), list):
        for q in obj["queries"]:
            query = str(q.get("query") if isinstance(q, dict) else q).strip()
            if query:
                reason = ""
                if isinstance(q, dict):
                    reason = str(q.get("reason") or q.get("aim") or q.get("when_to_use") or "").strip()
                query_items.append(
                    {
                        "query": query,
                        "reason": reason or f"show when transcript mentions {query}",
                    }
                )
    if not query_items:
        query_items = [
            {
                "query": query,
                "reason": f"keyword fallback query from transcript: {query}",
            }
            for query in _fallback_queries(transcript, query_count)
        ]
    proper_names = _proper_name_queries(transcript, limit=query_count)
    existing_queries = {item["query"].lower() for item in query_items}
    forced_name_items = [
        {
            "query": name,
            "reason": f"direct famous/known person query from transcript: {name}",
        }
        for name in proper_names
        if name.lower() not in existing_queries
    ]
    if forced_name_items:
        query_items = forced_name_items + query_items
    query_items = query_items[:query_count]
    # Crawl mode is intentionally reusable across runs. Keep all downloaded
    # safe-license assets in one flat library so future edits can use them.
    crawl_root = CRAWLED_DATA_DIR
    crawl_root.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    for idx, item in enumerate(query_items, start=1):
        query = item["query"]
        reason = item["reason"]
        rows = crawl_one_gif_one_image(
            query,
            crawl_root,
            filename_prefix=f"q{idx:02d}_",
        )
        for row in rows:
            original_about = str(row.get("about") or "").strip()
            media_type = str(row.get("type") or "").strip().lower()
            row["source_about"] = original_about
            row["crawl_query"] = query
            # For planner matching, keep crawl media intentionally grounded:
            # about is the search query plus the media form, aim is why base
            # planner chose it. This prevents image/gif pairs from looking like
            # duplicate entries in the planner prompt.
            if media_type == "gif":
                row["about"] = f"funny gif about {query}"
            elif media_type == "image":
                row["about"] = f"image of {query}"
            elif media_type == "video":
                row["about"] = f"video of {query}"
            else:
                row["about"] = query
            row["aim"] = reason
            row["selection_reason"] = reason
            row["transcript_part"] = reason
        all_rows.extend(rows)
    if all_rows:
        captions_path = _write_crawled_data_captions(all_rows, crawl_root / "captions.txt")
        write_text(debug_dir / "captions.txt", captions_path.read_text(encoding="utf-8", errors="ignore"))
        write_json(
            debug_dir / "crawl_summary.json",
            {
                "crawled_data_dir": str(crawl_root).replace("\\", "/"),
                "captions_path": str(captions_path).replace("\\", "/"),
                "queries": query_items,
                "downloaded_count": len(all_rows),
                "media_policy": "one_gif_and_one_image_per_query",
            },
        )
        print(f"[OPTIONAL_MEDIA] crawl assets saved in reusable folder: {crawl_root}")
        print(f"[OPTIONAL_MEDIA] crawl captions written: {captions_path}")
    return _to_optional_rows(all_rows, "crawl", len(all_rows))


def _collect_generate_prompts(
    transcript: str,
    user_instruction: str,
    base_planner_endpoint: str | None,
    collected_assets_dir: str | Path,
    optional_media_count: int,
    debug_dir: Path,
) -> list[dict[str, Any]]:
    template = _read_prompt_template(
        "base_generate_media_prompts.md",
        """
Generate AI media prompt ideas for an A2V edit.
Return valid JSON only: {{"generated_media":[{{"type":"image","prompt":"...","about":"...","aim":"show when relevant caption topic is spoken"}}]}}
TRANSCRIPT:
{transcript}
USER INSTRUCTION:
{user_instruction}
""",
    )
    prompt = template.format(transcript=transcript, user_instruction=user_instruction, optional_media_count=optional_media_count)
    obj = _call_base_planner(base_planner_endpoint, prompt, debug_dir)
    generated: list[dict[str, Any]] = []
    if isinstance(obj, dict) and isinstance(obj.get("generated_media"), list):
        generated = [g for g in obj["generated_media"] if isinstance(g, dict)][: max(0, optional_media_count)]
    if not generated:
        generated = [
            {
                "type": "image",
                "prompt": f"Clean vertical editorial image about {kw}, cinematic lighting, safe for all audiences",
                "about": f"Generated placeholder concept for {kw}.",
                "aim": "show when relevant caption topic is spoken",
            }
            for kw in _fallback_queries(transcript, optional_media_count)
        ][: max(0, optional_media_count)]
    gen_root = Path(collected_assets_dir) / "generate"
    gen_root.mkdir(parents=True, exist_ok=True)
    write_json(gen_root / "generated_media_prompts.json", {"generated_media": generated})
    write_json(debug_dir / "generated_media_prompts.json", {"generated_media": generated})
    # No actual generated files exist yet. Keep these as future assets, but do
    # not insert missing paths into planner media because they cannot render.
    return []


def collect_optional_media(
    mode: str,
    transcript: str,
    user_instruction: str,
    edit_name: str,
    base_planner_endpoint: str | None,
    asset_library_dir: str | Path,
    collected_assets_dir: str | Path,
    optional_media_count: int = 10,
    crawl_total_per_query: int = 8,
    crawl_funny_percent: int = 30,
    debug_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    mode = (mode or "none").strip().lower()
    if mode not in MODES:
        raise ValueError(f"media collection mode must be one of {sorted(MODES)}, got {mode}")
    optional_media_count = _clamp_optional_media_count(optional_media_count)
    dbg = _debug_root(edit_name, debug_dir)
    print(f"[OPTIONAL_MEDIA] mode={mode} debug_dir={dbg}")
    write_text(dbg / "mode.txt", mode)
    if mode == "none":
        write_json(dbg / "selected_optional_media.json", [])
        print("[OPTIONAL_MEDIA] mode none; no optional media collection.")
        return []
    if mode == "library":
        selected = _select_library_media(
            transcript,
            user_instruction,
            base_planner_endpoint,
            asset_library_dir,
            optional_media_count,
            dbg,
        )
    elif mode == "crawl":
        selected = _collect_crawl_media(
            transcript,
            user_instruction,
            edit_name,
            base_planner_endpoint,
            collected_assets_dir,
            optional_media_count,
            crawl_total_per_query,
            crawl_funny_percent,
            dbg,
        )
    else:
        selected = _collect_generate_prompts(
            transcript,
            user_instruction,
            base_planner_endpoint,
            collected_assets_dir,
            optional_media_count,
            dbg,
        )
    write_json(dbg / "selected_optional_media.json", selected)
    print(f"[OPTIONAL_MEDIA] wrote selected optional media: {dbg / 'selected_optional_media.json'} count={len(selected)}")
    return selected
