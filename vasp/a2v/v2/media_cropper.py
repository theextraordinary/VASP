from __future__ import annotations

import csv
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


CROP_PATTERN = re.compile(r"\bcrop\s*:\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)
FILENAME_KEYS = ("file", "media_name", "filename", "file_name", "image", "video", "media")
AIM_KEYS = ("aim", "usage", "intent")
TEXT_KEYS = AIM_KEYS + ("about", "caption", "description", "text")
TRIMMABLE_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".ogv", ".gif", ".mp3", ".wav", ".m4a", ".aac"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac"}


def _detect_delimiter(text: str) -> str:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if "\t" in first_line:
        return "\t"
    return ","


def _find_key(keys: Any, candidates: tuple[str, ...]) -> str | None:
    lowered = {str(k).strip().lower(): k for k in keys}
    for candidate in candidates:
        if candidate in lowered:
            return str(lowered[candidate])
    return None


def _crop_suffix(start: float, end: float) -> str:
    def fmt(v: float) -> str:
        text = f"{v:g}".replace(".", "p")
        return re.sub(r"[^0-9p]+", "", text)

    return f"crop_{fmt(start)}_{fmt(end)}"


def _trimmed_path(src: Path, start: float, end: float) -> Path:
    suffix = _crop_suffix(start, end)
    candidate = src.with_name(f"{src.stem}_{suffix}{src.suffix}")
    idx = 2
    while candidate.exists() and candidate.resolve() == src.resolve():
        candidate = src.with_name(f"{src.stem}_{suffix}_{idx}{src.suffix}")
        idx += 1
    return candidate


def _run_ffmpeg_trim(src: Path, dst: Path, start: float, end: float) -> None:
    duration = max(0.0, end - start)
    if duration <= 0:
        raise ValueError(f"invalid crop duration for {src.name}: {start}-{end}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    base_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
        "-map",
        "0",
    ]
    copy_cmd = base_cmd + ["-c", "copy", "-avoid_negative_ts", "make_zero", str(dst)]
    try:
        subprocess.run(copy_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if dst.exists() and dst.stat().st_size > 0:
            return
    except Exception:
        pass

    if src.suffix.lower() in AUDIO_EXTENSIONS:
        fallback_cmd = base_cmd + ["-vn", "-c:a", "aac" if dst.suffix.lower() in {".m4a", ".aac"} else "libmp3lame", str(dst)]
    else:
        fallback_cmd = base_cmd + ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(dst)]
    subprocess.run(fallback_cmd, check=True)


def _resolve_media_path(captions_dir: Path, filename: str) -> Path | None:
    raw = str(filename or "").strip().strip('"').strip("'")
    if not raw:
        return None
    direct = captions_dir / raw
    if direct.exists():
        return direct
    raw_path = Path(raw)
    if raw_path.exists():
        return raw_path
    lower = raw.lower()
    for path in captions_dir.iterdir():
        if path.is_file() and path.name.lower() == lower:
            return path
    stem = raw_path.stem.lower()
    for path in captions_dir.iterdir():
        if path.is_file() and path.stem.lower() == stem:
            return path
    return None


def _extract_crop(row: dict[str, str]) -> tuple[float, float] | None:
    values: list[str] = []
    for key in TEXT_KEYS:
        for actual_key, value in row.items():
            if str(actual_key).strip().lower() == key:
                values.append(str(value or ""))
    if not values:
        values = [str(v or "") for v in row.values()]
    joined = " ".join(values)
    match = CROP_PATTERN.search(joined)
    if not match:
        return None
    start = float(match.group(1))
    end = float(match.group(2))
    if end <= start:
        return None
    return start, end


def apply_crop_directives_to_captions_file(captions_file_path: str | Path) -> dict[str, Any]:
    """Trim media rows that contain `crop:x-y` and rewrite the captions file.

    The original media is not deleted. A trimmed copy is created in the same
    folder and the captions row is updated to point at the trimmed filename.
    A `.pre_crop.bak` backup is written before the first in-place update.
    """

    captions_path = Path(captions_file_path)
    report: dict[str, Any] = {
        "captions_file": str(captions_path).replace("\\", "/"),
        "updated": False,
        "trimmed": [],
        "warnings": [],
    }
    if not captions_path.exists():
        report["warnings"].append("captions_file_missing")
        return report

    text = captions_path.read_text(encoding="utf-8-sig", errors="ignore")
    if "crop:" not in text.lower():
        return report

    delimiter = _detect_delimiter(text)
    lines = text.splitlines()
    if not lines:
        return report
    reader = csv.DictReader(lines, delimiter=delimiter)
    if not reader.fieldnames:
        report["warnings"].append("captions_file_has_no_header")
        return report

    rows = list(reader)
    file_key = _find_key(reader.fieldnames, FILENAME_KEYS)
    if not file_key:
        report["warnings"].append("captions_file_missing_filename_column")
        return report

    changed = False
    captions_dir = captions_path.parent
    for idx, row in enumerate(rows):
        crop = _extract_crop(row)
        if not crop:
            continue
        filename = str(row.get(file_key) or "").strip()
        src = _resolve_media_path(captions_dir, filename)
        if not src:
            report["warnings"].append(f"crop_source_not_found:row_{idx + 2}:{filename}")
            continue
        if src.suffix.lower() not in TRIMMABLE_EXTENSIONS:
            report["warnings"].append(f"crop_unsupported_extension:row_{idx + 2}:{src.name}")
            continue
        start, end = crop
        dst = _trimmed_path(src, start, end)
        if not dst.exists() or dst.stat().st_size <= 0:
            _run_ffmpeg_trim(src, dst, start, end)
        row[file_key] = dst.name
        changed = True
        report["trimmed"].append(
            {
                "row": idx + 2,
                "source": src.name,
                "trimmed": dst.name,
                "start": start,
                "end": end,
            }
        )

    if changed:
        backup = captions_path.with_suffix(captions_path.suffix + ".pre_crop.bak")
        if not backup.exists():
            shutil.copy2(captions_path, backup)
        with captions_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=reader.fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
        report["updated"] = True
        report["backup"] = str(backup).replace("\\", "/")
    return report
