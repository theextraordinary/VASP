from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from vasp.media_reader.pipeline import generate_input_json


def create_media_json_from_captions_file(
    *,
    captions_file_path: str | Path,
    output_media_json_path: str | Path = "output/media.json",
    instruction: str = "Create a caption-aware edit using provided media.",
    default_image_aim: str = "show when relevant caption topic is spoken",
) -> dict[str, Any]:
    """Build media.json from a captions file and media files in the same directory.

    Expected captions format (CSV):
    - Header style (recommended): `image,caption` or `filename,caption`
    - Repeated rows per same filename are allowed.
    - About for each media file is taken as the first non-empty caption for that file.
    """
    captions_path = Path(captions_file_path)
    if not captions_path.exists():
        raise FileNotFoundError(f"captions file not found: {captions_path}")

    media_dir = captions_path.parent
    file_to_meta = _parse_file_meta_map(captions_path)
    if not file_to_meta:
        raise ValueError(f"No valid filename/about pairs found in: {captions_path}")

    media_files = [p for p in media_dir.iterdir() if p.is_file()]
    media_items: list[tuple[str, str | None, str | None]] = []
    unresolved: list[str] = []
    for filename, meta in file_to_meta.items():
        about = str(meta.get("about", "") or "").strip()
        aim_from_file = str(meta.get("aim", "") or "").strip()
        media_path = _resolve_media_file(media_files, filename)
        if media_path is None:
            unresolved.append(filename)
            continue
        suffix = media_path.suffix.lower()
        if aim_from_file:
            aim = aim_from_file
        elif suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            aim = default_image_aim
        elif suffix in {".mp3", ".wav", ".m4a", ".aac", ".mp4", ".mov", ".mkv", ".avi"}:
            aim = "extract speech captions"
        else:
            aim = None
        media_items.append((str(media_path), aim, about))

    if not media_items:
        details = ""
        if unresolved:
            details = f" Unresolved entries: {unresolved[:8]}"
        raise ValueError("No media files from captions file were found in the same directory." + details)

    payload = generate_input_json(
        instruction=instruction,
        media_paths=media_items,
        output_path=None,
        options={
            "asr_enabled": True,
            "asr_model_size": "small",
            # Only first file is treated as main input for ASR.
            "asr_only_first_input": True,
        },
    )

    out_path = Path(output_media_json_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _resolve_media_file(media_files: list[Path], filename_hint: str) -> Path | None:
    """Resolve captions file key to an actual media file in same directory."""
    hint = str(filename_hint).strip().strip('"').strip("'")
    if not hint:
        return None

    # 1) exact name
    for p in media_files:
        if p.name == hint:
            return p

    hint_lower = hint.lower()
    # 2) case-insensitive exact name
    for p in media_files:
        if p.name.lower() == hint_lower:
            return p

    hint_stem = Path(hint).stem.lower()
    # 3) exact stem match
    stem_matches = [p for p in media_files if p.stem.lower() == hint_stem]
    if stem_matches:
        return _pick_best_match(stem_matches, hint_lower)

    # 4) normalized slug/stem match (handles spaces, punctuation, missing extension)
    norm_hint = _norm_token(hint_stem)
    norm_matches = [p for p in media_files if _norm_token(p.stem) == norm_hint]
    if norm_matches:
        return _pick_best_match(norm_matches, hint_lower)

    # 5) fallback contains match on stem
    contains_matches = [p for p in media_files if hint_stem and hint_stem in p.stem.lower()]
    if contains_matches:
        return _pick_best_match(contains_matches, hint_lower)

    return None


def _norm_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _pick_best_match(candidates: list[Path], hint_lower: str) -> Path:
    audio_ext = {".m4a", ".mp3", ".wav", ".aac"}
    if "audio" in hint_lower:
        audio_candidates = [p for p in candidates if p.suffix.lower() in audio_ext]
        if audio_candidates:
            return sorted(audio_candidates, key=lambda p: p.name.lower())[0]
    return sorted(candidates, key=lambda p: p.name.lower())[0]


def _parse_file_meta_map(captions_path: Path) -> dict[str, dict[str, str]]:
    """Return filename -> {about, aim} from CSV-like file.

    Supported columns:
    - `file_name,about,aim` (preferred)
    - `image,caption,aim`
    - legacy 2-column `filename,about` (aim optional/empty)
    """
    text = captions_path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return {}

    # Try DictReader first
    rows = list(csv.DictReader(text.splitlines()))
    if rows:
        file_key = _find_key(rows[0].keys(), ["image", "file_name", "filename", "file", "path", "media"])
        cap_key = _find_key(rows[0].keys(), ["caption", "about", "description", "text"])
        if file_key and cap_key:
            aim_key = _find_key(rows[0].keys(), ["aim", "usage", "intent"])
            out: dict[str, dict[str, str]] = {}
            for row in rows:
                raw_file = str(row.get(file_key, "")).strip()
                raw_caption = str(row.get(cap_key, "")).strip()
                raw_aim = str(row.get(aim_key, "")).strip() if aim_key else ""
                if not raw_file or not raw_caption:
                    continue
                # Keep first row for each file to preserve order and deterministic mapping.
                out.setdefault(raw_file, {"about": raw_caption, "aim": raw_aim})
            return out

    # Fallback: plain CSV rows [filename, caption]
    out_fallback: dict[str, dict[str, str]] = {}
    for rec in csv.reader(text.splitlines()):
        if len(rec) < 2:
            continue
        filename = str(rec[0]).strip()
        about = str(rec[1]).strip()
        aim = str(rec[2]).strip() if len(rec) > 2 else ""
        if not filename or not about:
            continue
        # Skip header-like first row.
        if filename.lower() in {"image", "filename", "file", "path", "media"}:
            continue
        out_fallback.setdefault(filename, {"about": about, "aim": aim})
    return out_fallback


def _find_key(keys: Any, candidates: list[str]) -> str | None:
    key_list = [str(k).strip() for k in keys]
    lowered = {k.lower(): k for k in key_list}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build media.json using captions CSV and media files in the same directory "
            "(filename/about mapping from captions file)."
        )
    )
    parser.add_argument(
        "--captions-file",
        required=True,
        help="Path to captions CSV/txt file (e.g., file_name,about,aim). Media files are read from same directory.",
    )
    parser.add_argument("--output-media-json", default="output/media.json")
    parser.add_argument(
        "--instruction",
        default="Create a caption-aware edit using provided media.",
        help="Instruction to store in media.json intent.",
    )
    args = parser.parse_args()

    payload = create_media_json_from_captions_file(
        captions_file_path=args.captions_file,
        output_media_json_path=args.output_media_json,
        instruction=args.instruction,
    )
    print(
        json.dumps(
            {
                "output_media_json": str(Path(args.output_media_json)),
                "media_count": len((payload.get("media_context") or {}).get("inputs", [])),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
