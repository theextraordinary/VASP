from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return path.read_text(encoding="utf-8").strip()


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Append planner/refiner supervised rows for A2V tuning.")
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--element-compact", default="output/element2_compact.txt")
    parser.add_argument("--planner-text", default="output/planner.txt")
    parser.add_argument("--inter-json", default="output/inter.json")
    parser.add_argument("--out", default="finetune/data/a2v_curated_seed.jsonl")
    parser.add_argument("--append-planner", action="store_true")
    parser.add_argument("--append-refiner", action="store_true")
    args = parser.parse_args()

    element_compact = _read_text(Path(args.element_compact))
    out = Path(args.out)

    if args.append_planner:
        planner_text = _read_text(Path(args.planner_text))
        row = {
            "task": "planner_text",
            "messages": [
                {
                    "role": "system",
                    "content": "You are VASP Planner. Return ONLY EDIT PLAN text with fixed headings. No JSON.",
                },
                {
                    "role": "user",
                    "content": f"USER_INSTRUCTION: {args.instruction}\nELEMENT_COMPACT:\n{element_compact}",
                },
                {"role": "assistant", "content": planner_text},
            ],
        }
        _append_jsonl(out, row)
        print(f"[dataset] appended planner row -> {out}")

    if args.append_refiner:
        planner_text = _read_text(Path(args.planner_text))
        inter_json = _read_text(Path(args.inter_json))
        row = {
            "task": "refiner_inter_json",
            "messages": [
                {
                    "role": "system",
                    "content": "You are VASP Refiner. Return ONLY valid inter.json with renderer-useful fields.",
                },
                {
                    "role": "user",
                    "content": (
                        f"USER_INSTRUCTION: {args.instruction}\n"
                        f"PLANNER_TEXT:\n{planner_text}\n"
                        f"ELEMENT_COMPACT:\n{element_compact}"
                    ),
                },
                {"role": "assistant", "content": inter_json},
            ],
        }
        _append_jsonl(out, row)
        print(f"[dataset] appended refiner row -> {out}")

    if not args.append_planner and not args.append_refiner:
        raise SystemExit("Nothing to do. Use --append-planner and/or --append-refiner.")


if __name__ == "__main__":
    main()

