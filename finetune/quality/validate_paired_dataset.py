from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from finetune.quality.contracts import check_planner_output, check_refiner_text


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _msg(row: dict[str, Any], role: str) -> str:
    for m in row.get("messages", []):
        if m.get("role") == role:
            return str(m.get("content", ""))
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate planner/refiner paired dataset with strict contracts.")
    ap.add_argument("--planner", default="finetune/data/planner_train_paired.jsonl")
    ap.add_argument("--refiner", default="finetune/data/refiner_train_paired.jsonl")
    ap.add_argument("--out", default="output/quality/paired_validation_report.json")
    args = ap.parse_args()

    planner_rows = _load_jsonl(Path(args.planner))
    refiner_rows = _load_jsonl(Path(args.refiner))
    p_map = {r.get("id", "").replace("planner_", ""): r for r in planner_rows}
    r_map = {r.get("id", "").replace("refiner_", ""): r for r in refiner_rows}
    common = sorted(set(p_map) & set(r_map))

    report: dict[str, Any] = {
        "total_planner": len(planner_rows),
        "total_refiner": len(refiner_rows),
        "paired_common": len(common),
        "planner_contract_ok": 0,
        "refiner_contract_ok": 0,
        "both_ok": 0,
        "failed_samples": [],
    }

    for sid in common:
        prow = p_map[sid]
        rrow = r_map[sid]
        p_user = _msg(prow, "user")
        p_assistant = _msg(prow, "assistant")
        r_assistant = _msg(rrow, "assistant")

        planner_check = check_planner_output(p_assistant, user_prompt=p_user)
        refiner_check = check_refiner_text(r_assistant, planner_text=p_assistant)

        if planner_check.ok:
            report["planner_contract_ok"] += 1
        if refiner_check.ok:
            report["refiner_contract_ok"] += 1
        if planner_check.ok and refiner_check.ok:
            report["both_ok"] += 1
        else:
            report["failed_samples"].append(
                {
                    "id": sid,
                    "planner_ok": planner_check.ok,
                    "planner_score": planner_check.score,
                    "planner_errors": planner_check.errors,
                    "planner_details": planner_check.details,
                    "refiner_ok": refiner_check.ok,
                    "refiner_score": refiner_check.score,
                    "refiner_errors": refiner_check.errors,
                    "refiner_details": refiner_check.details,
                }
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    print(
        {
            "paired_common": report["paired_common"],
            "planner_contract_ok": f"{report['planner_contract_ok']}/{report['paired_common']}",
            "refiner_contract_ok": f"{report['refiner_contract_ok']}/{report['paired_common']}",
            "both_ok": f"{report['both_ok']}/{report['paired_common']}",
        }
    )


if __name__ == "__main__":
    main()

