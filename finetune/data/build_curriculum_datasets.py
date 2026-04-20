from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _split(rows: list[dict[str, Any]], val_ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows_sorted = sorted(rows, key=lambda r: str(r.get("id", "")))
    n_val = max(1, int(round(len(rows_sorted) * val_ratio)))
    return rows_sorted[n_val:], rows_sorted[:n_val]


def _msg(row: dict[str, Any], role: str) -> str:
    for m in row.get("messages", []):
        if m.get("role") == role:
            return str(m.get("content", ""))
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Stage A/B/C curriculum datasets.")
    ap.add_argument("--planner", default="finetune/data/planner_train_paired.jsonl")
    ap.add_argument("--refiner", default="finetune/data/refiner_train_paired.jsonl")
    ap.add_argument("--out-dir", default="finetune/data/curriculum")
    ap.add_argument("--val-ratio", type=float, default=0.05)
    args = ap.parse_args()

    planner_rows = _load_jsonl(Path(args.planner))
    refiner_rows = _load_jsonl(Path(args.refiner))

    # Stage A: planner-only format discipline.
    stage_a = [r for r in planner_rows if str(r.get("id", "")).startswith("planner_")]

    # Stage B: refiner-only schema fidelity.
    stage_b = [r for r in refiner_rows if str(r.get("id", "")).startswith("refiner_")]

    # Stage C: end-to-end robustness.
    # We keep refiner task but inject planner text from paired planner row (already in user prompt).
    # Duplicate as explicit e2e rows for curriculum scheduling.
    p_map = {str(r.get("id", "")).replace("planner_", ""): r for r in stage_a}
    stage_c: list[dict[str, Any]] = []
    for rr in stage_b:
        sid = str(rr.get("id", "")).replace("refiner_", "")
        pr = p_map.get(sid)
        if pr is None:
            continue
        stage_c.append(
            {
                "task": "refiner_e2e",
                "id": f"refiner_e2e_{sid}",
                "messages": rr.get("messages", []),
                "meta": {
                    "paired_planner_id": pr.get("id"),
                    "planner_has_grouping_rules": ("1-5 words" in _msg(pr, "assistant")),
                },
            }
        )

    out_dir = Path(args.out_dir)
    for name, rows in [("stage_a_planner", stage_a), ("stage_b_refiner", stage_b), ("stage_c_e2e", stage_c)]:
        tr, va = _split(rows, args.val_ratio)
        _write_jsonl(out_dir / f"{name}_train.jsonl", tr)
        _write_jsonl(out_dir / f"{name}_val.jsonl", va)
        print(f"[{name}] train={len(tr)} val={len(va)} total={len(rows)}")


if __name__ == "__main__":
    main()

