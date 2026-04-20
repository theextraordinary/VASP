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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _msg(row: dict[str, Any], role: str) -> str:
    for m in row.get("messages", []):
        if m.get("role") == role:
            return str(m.get("content", ""))
    return ""


def _split(rows: list[dict[str, Any]], val_ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda r: str(r.get("id", "")))
    if not ordered:
        return [], []
    n_val = max(1, int(round(len(ordered) * val_ratio)))
    return ordered[n_val:], ordered[:n_val]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build hard negatives and DPO pairs from endpoint eval outputs.")
    ap.add_argument("--endpoint-eval-dir", default="output/endpoint_eval")
    ap.add_argument("--planner", default="finetune/data/planner_train_paired.jsonl")
    ap.add_argument("--refiner", default="finetune/data/refiner_train_paired.jsonl")
    ap.add_argument("--out-dir", default="finetune/data/hardneg")
    ap.add_argument("--val-ratio", type=float, default=0.1)
    args = ap.parse_args()

    eval_dir = Path(args.endpoint_eval_dir)
    report = json.loads((eval_dir / "endpoint_eval_report.json").read_text(encoding="utf-8"))
    planner_rows = _load_jsonl(Path(args.planner))
    refiner_rows = _load_jsonl(Path(args.refiner))
    p_map = {str(r.get("id", "")).replace("planner_", ""): r for r in planner_rows}
    r_map = {str(r.get("id", "")).replace("refiner_", ""): r for r in refiner_rows}

    planner_hard_sft: list[dict[str, Any]] = []
    refiner_hard_sft: list[dict[str, Any]] = []
    planner_dpo: list[dict[str, Any]] = []
    refiner_dpo: list[dict[str, Any]] = []

    ids = set(report.get("independent_ids", [])) | set(report.get("e2e_ids", []))
    for sid in sorted(ids):
        pr = p_map.get(sid)
        rr = r_map.get(sid)
        if pr is None or rr is None:
            continue

        p_user = _msg(pr, "user")
        p_gold = _msg(pr, "assistant")
        r_user = _msg(rr, "user")
        r_gold = _msg(rr, "assistant")

        p_pred = _read(eval_dir / f"independent_planner_pred_{sid}.txt") or _read(eval_dir / f"e2e_planner_pred_{sid}.txt")
        r_pred = _read(eval_dir / f"independent_refiner_pred_{sid}.txt") or _read(eval_dir / f"e2e_refiner_pred_{sid}.txt")

        # SFT hard negatives = keep gold response for failed ids (upweight by duplication).
        if p_pred and p_pred.strip() and p_pred.strip() != p_gold.strip():
            planner_hard_sft.append(pr)
        if r_pred and r_pred.strip() and r_pred.strip() != r_gold.strip():
            refiner_hard_sft.append(rr)

        # DPO pairs.
        if p_pred.strip() and p_pred.strip() != p_gold.strip():
            planner_dpo.append(
                {
                    "id": f"dpo_planner_{sid}",
                    "task": "planner_dpo",
                    "prompt": p_user,
                    "chosen": p_gold,
                    "rejected": p_pred,
                }
            )
        if r_pred.strip() and r_pred.strip() != r_gold.strip():
            refiner_dpo.append(
                {
                    "id": f"dpo_refiner_{sid}",
                    "task": "refiner_dpo",
                    "prompt": r_user,
                    "chosen": r_gold,
                    "rejected": r_pred,
                }
            )

    out_dir = Path(args.out_dir)
    _write_jsonl(out_dir / "planner_hardneg_sft.jsonl", planner_hard_sft)
    _write_jsonl(out_dir / "refiner_hardneg_sft.jsonl", refiner_hard_sft)
    _write_jsonl(out_dir / "planner_dpo_pairs.jsonl", planner_dpo)
    _write_jsonl(out_dir / "refiner_dpo_pairs.jsonl", refiner_dpo)
    p_tr, p_va = _split(planner_dpo, args.val_ratio)
    r_tr, r_va = _split(refiner_dpo, args.val_ratio)
    _write_jsonl(out_dir / "planner_dpo_train.jsonl", p_tr)
    _write_jsonl(out_dir / "planner_dpo_val.jsonl", p_va)
    _write_jsonl(out_dir / "refiner_dpo_train.jsonl", r_tr)
    _write_jsonl(out_dir / "refiner_dpo_val.jsonl", r_va)

    print(
        {
            "planner_hardneg_sft": len(planner_hard_sft),
            "refiner_hardneg_sft": len(refiner_hard_sft),
            "planner_dpo_pairs": len(planner_dpo),
            "refiner_dpo_pairs": len(refiner_dpo),
            "planner_dpo_train": len(p_tr),
            "planner_dpo_val": len(p_va),
            "refiner_dpo_train": len(r_tr),
            "refiner_dpo_val": len(r_va),
        }
    )


if __name__ == "__main__":
    main()
