from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _merge(base_rows: list[dict[str, Any]], extra_rows: list[dict[str, Any]], upweight: int) -> list[dict[str, Any]]:
    merged = list(base_rows)
    for row in extra_rows:
        for _ in range(max(1, upweight)):
            merged.append(row)
    return merged


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge hard-negative SFT rows into base paired train sets.")
    ap.add_argument("--planner-base", default="finetune/data/planner_paired_train.jsonl")
    ap.add_argument("--refiner-base", default="finetune/data/refiner_paired_train.jsonl")
    ap.add_argument("--planner-hardneg", default="finetune/data/hardneg/planner_hardneg_sft.jsonl")
    ap.add_argument("--refiner-hardneg", default="finetune/data/hardneg/refiner_hardneg_sft.jsonl")
    ap.add_argument("--upweight", type=int, default=3)
    ap.add_argument("--out-dir", default="finetune/data/curriculum")
    args = ap.parse_args()

    planner_base = _load_jsonl(Path(args.planner_base))
    refiner_base = _load_jsonl(Path(args.refiner_base))
    planner_hn = _load_jsonl(Path(args.planner_hardneg))
    refiner_hn = _load_jsonl(Path(args.refiner_hardneg))

    planner_out = _merge(planner_base, planner_hn, args.upweight)
    refiner_out = _merge(refiner_base, refiner_hn, args.upweight)

    out_dir = Path(args.out_dir)
    _write_jsonl(out_dir / "planner_stageA_plus_hardneg_train.jsonl", planner_out)
    _write_jsonl(out_dir / "refiner_stageB_plus_hardneg_train.jsonl", refiner_out)
    print(
        {
            "planner_base": len(planner_base),
            "planner_hardneg": len(planner_hn),
            "planner_out": len(planner_out),
            "refiner_base": len(refiner_base),
            "refiner_hardneg": len(refiner_hn),
            "refiner_out": len(refiner_out),
        }
    )


if __name__ == "__main__":
    main()

