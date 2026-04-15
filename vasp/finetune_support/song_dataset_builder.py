from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from vasp.a2v.transcription import transcribe_media_with_features
from vasp.media_reader.probe import probe_media

def build_song_chunks_and_sync_examples(
    *,
    input_folder: str,
    assets_input_dir: str = "assets/inputs",
    dataset_dir: str = "finetune/data",
    chunk_seconds: float = 30.0,
    asr_model_size: str = "small",
    mapping_output_filename: str = "song_word_maps.json",
) -> dict[str, Any]:
    """
    1) Split every .m4a file from `input_folder` into 30s chunks: song_*.m4a in assets/inputs.
    2) Run Whisper transcription on each chunk and save ONLY word-timing map JSON.
    3) Create one aggregate JSON with {audio_path, word_timing_map}.
    """
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be > 0")

    in_dir = Path(input_folder)
    if not in_dir.exists():
        raise FileNotFoundError(f"input_folder not found: {in_dir}")

    assets_dir = Path(assets_input_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(dataset_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_files = sorted(in_dir.glob("*.m4a"))
    if not source_files:
        raise FileNotFoundError(f"No .m4a files found in: {in_dir}")

    chunk_manifest: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []

    global_chunk_idx = _next_song_chunk_index(assets_dir)

    for source in source_files:
        probe = probe_media(str(source))
        duration = float(probe.duration or 0.0)
        if duration <= 0:
            continue
        num_chunks = int(math.ceil(duration / chunk_seconds))

        for n in range(num_chunks):
            start = n * chunk_seconds
            chunk_dur = min(chunk_seconds, duration - start)
            if chunk_dur <= 0.01:
                continue

            chunk_name = f"song_{global_chunk_idx:04d}.m4a"
            chunk_path = assets_dir / chunk_name
            _trim_audio_chunk(source=source, out_path=chunk_path, start_s=start, dur_s=chunk_dur)

            transcript = transcribe_media_with_features(str(chunk_path), model_size=asr_model_size)
            words = _normalize_words(transcript.get("words", []))
            whisper_json_path = assets_dir / f"song_{global_chunk_idx:04d}_whisper.json"
            # Per-file JSON should contain only word-to-time mapping.
            whisper_json_path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")

            audio_path_str = str(chunk_path).replace("\\", "/")
            aggregate_rows.append({"audio_path": audio_path_str, "word_timing_map": words})

            if not words:
                global_chunk_idx += 1
                chunk_manifest.append(
                    {
                        "chunk_id": chunk_name,
                        "source_file": str(source),
                        "start": round(start, 3),
                        "end": round(start + chunk_dur, 3),
                        "duration": round(chunk_dur, 3),
                        "whisper_json": str(whisper_json_path),
                        "word_count": 0,
                    }
                )
                continue

            chunk_manifest.append(
                {
                    "chunk_id": chunk_name,
                    "source_file": str(source),
                    "start": round(start, 3),
                    "end": round(start + chunk_dur, 3),
                    "duration": round(chunk_dur, 3),
                    "whisper_json": str(whisper_json_path),
                    "word_count": len(words),
                }
            )
            global_chunk_idx += 1

    mapping_path = out_dir / mapping_output_filename
    manifest_path = out_dir / "song_chunks_manifest.json"
    mapping_path.write_text(json.dumps(aggregate_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(chunk_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "songs_found": len(source_files),
        "chunks_created": len(chunk_manifest),
        "mappings_saved": len(aggregate_rows),
        "mapping_file": str(mapping_path),
        "manifest_file": str(manifest_path),
    }


def refresh_existing_song_whisper_maps(
    *,
    assets_input_dir: str = "assets/inputs",
    dataset_dir: str = "finetune/data",
    asr_model_size: str = "small",
    mapping_output_filename: str = "song_word_maps.json",
) -> dict[str, Any]:
    """
    Re-transcribe all existing assets/inputs/song_*.m4a and overwrite
    song_*_whisper.json with ONLY word-timing mappings.
    """
    assets_dir = Path(assets_input_dir)
    out_dir = Path(dataset_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    m4a_files = sorted(assets_dir.glob("song_*.m4a"))
    if not m4a_files:
        raise FileNotFoundError(f"No song_*.m4a files found in: {assets_dir}")

    aggregate_rows: list[dict[str, Any]] = []
    updated = 0
    skipped_empty = 0
    for song_path in m4a_files:
        transcript = transcribe_media_with_features(str(song_path), model_size=asr_model_size)
        words = _normalize_words(transcript.get("words", []))
        out_json = song_path.with_name(f"{song_path.stem}_whisper.json")
        # Never wipe existing mappings with empty output (e.g., whisperx missing).
        if words:
            out_json.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
            updated += 1
        else:
            skipped_empty += 1
            if not out_json.exists():
                out_json.write_text("[]", encoding="utf-8")
            try:
                words = json.loads(out_json.read_text(encoding="utf-8"))
                if not isinstance(words, list):
                    words = []
            except Exception:
                words = []
        aggregate_rows.append(
            {
                "audio_path": str(song_path).replace("\\", "/"),
                "word_timing_map": words,
            }
        )

    mapping_path = out_dir / mapping_output_filename
    mapping_path.write_text(json.dumps(aggregate_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "songs_found": len(m4a_files),
        "maps_updated": updated,
        "maps_skipped_empty": skipped_empty,
        "mapping_file": str(mapping_path),
    }


def _trim_audio_chunk(*, source: Path, out_path: Path, start_s: float, dur_s: float) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_s:.3f}",
        "-t",
        f"{dur_s:.3f}",
        "-i",
        str(source),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _normalize_words(words: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(words, list):
        return out
    for w in words:
        if not isinstance(w, dict):
            continue
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        try:
            start = float(w.get("start", 0.0))
            end = float(w.get("end", start))
        except (TypeError, ValueError):
            continue
        if end < start:
            end = start
        out.append({"text": text, "start": round(start, 3), "end": round(end, 3)})
    return out


def _next_song_chunk_index(assets_dir: Path) -> int:
    idx = 1
    existing = sorted(assets_dir.glob("song_*.m4a"))
    if not existing:
        return idx
    numbers = []
    for p in existing:
        stem = p.stem
        try:
            numbers.append(int(stem.split("_")[-1]))
        except (TypeError, ValueError):
            continue
    return (max(numbers) + 1) if numbers else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split .m4a songs into 30s chunks, run Whisper word timing, and append planner/refiner sync examples."
        )
    )
    parser.add_argument("--input-folder", required=True, help="Folder containing source .m4a files.")
    parser.add_argument("--assets-input-dir", default="assets/inputs")
    parser.add_argument("--dataset-dir", default="finetune/data")
    parser.add_argument("--chunk-seconds", type=float, default=30.0)
    parser.add_argument("--asr-model-size", default="small")
    parser.add_argument("--mapping-output-filename", default="song_word_maps.json")
    parser.add_argument(
        "--refresh-existing-only",
        action="store_true",
        help="Skip chunking and only re-transcribe existing assets/inputs/song_*.m4a",
    )
    args = parser.parse_args()

    if args.refresh_existing_only:
        result = refresh_existing_song_whisper_maps(
            assets_input_dir=args.assets_input_dir,
            dataset_dir=args.dataset_dir,
            asr_model_size=args.asr_model_size,
            mapping_output_filename=args.mapping_output_filename,
        )
    else:
        result = build_song_chunks_and_sync_examples(
            input_folder=args.input_folder,
            assets_input_dir=args.assets_input_dir,
            dataset_dir=args.dataset_dir,
            chunk_seconds=args.chunk_seconds,
            asr_model_size=args.asr_model_size,
            mapping_output_filename=args.mapping_output_filename,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
