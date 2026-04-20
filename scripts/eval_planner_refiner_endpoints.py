from __future__ import annotations

import argparse
import difflib
import json
import os
import random
from pathlib import Path
from typing import Any

import requests
from finetune.quality.contracts import check_planner_output, check_refiner_text


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _msg(messages: list[dict[str, str]], role: str) -> str:
    for m in messages:
        if m.get("role") == role:
            return m.get("content", "")
    return ""


def _post_generate(url: str, prompt: str, max_tokens: int, temperature: float, timeout_s: int) -> str:
    resp = requests.post(
        url,
        json={"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature},
        timeout=timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()
    return str(data.get("response", "")).strip()


def _safe_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s : e + 1])
        except json.JSONDecodeError:
            return None
    return None


def _planner_check(text: str, user_prompt: str) -> dict[str, Any]:
    c = check_planner_output(text, user_prompt=user_prompt)
    return {"ok": c.ok, "score": c.score, "errors": c.errors, "details": c.details}


def _refiner_check(text: str, planner_text: str) -> dict[str, Any]:
    c = check_refiner_text(text, planner_text=planner_text)
    return {"ok": c.ok, "score": c.score, "errors": c.errors, "details": c.details}


def _replace_planner_text(refiner_user_prompt: str, planner_text: str) -> str:
    start = refiner_user_prompt.find("PLANNER_TEXT:")
    split = refiner_user_prompt.find("ELEMENT_COMPACT:")
    if start == -1 or split == -1 or split <= start:
        return refiner_user_prompt
    before = refiner_user_prompt[: start + len("PLANNER_TEXT:")]
    after = refiner_user_prompt[split:]
    return f"{before}\n{planner_text.strip()}\n{after}"


def _compare_inter(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    p_elems = pred.get("elements", []) if isinstance(pred.get("elements"), list) else []
    g_elems = gold.get("elements", []) if isinstance(gold.get("elements"), list) else []
    p_ids = {e.get("element_id") for e in p_elems if isinstance(e, dict)}
    g_ids = {e.get("element_id") for e in g_elems if isinstance(e, dict)}
    inter = p_ids & g_ids
    union = p_ids | g_ids
    jacc = (len(inter) / len(union)) if union else 1.0

    def _caption_actions(elems: list[dict[str, Any]]) -> int:
        for e in elems:
            if e.get("element_id") == "caption_track_1":
                acts = e.get("actions", [])
                return len(acts) if isinstance(acts, list) else 0
        return 0

    return {
        "pred_elements": len(p_elems),
        "gold_elements": len(g_elems),
        "element_id_jaccard": round(jacc, 4),
        "pred_caption_actions": _caption_actions(p_elems),
        "gold_caption_actions": _caption_actions(g_elems),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate planner/refiner endpoints on paired examples.")
    ap.add_argument("--planner-url", default=os.getenv("PLANNER_URL", ""), help="Planner /generate URL")
    ap.add_argument("--refiner-url", default=os.getenv("REFINER_URL", ""), help="Refiner /generate URL")
    ap.add_argument("--planner-jsonl", default="finetune/data/planner_train_paired.jsonl")
    ap.add_argument("--refiner-jsonl", default="finetune/data/refiner_train_paired.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-independent", type=int, default=5)
    ap.add_argument("--n-e2e", type=int, default=5)
    ap.add_argument("--timeout-s", type=int, default=600)
    ap.add_argument("--out-dir", default="output/endpoint_eval")
    args = ap.parse_args()

    if not args.planner_url or not args.refiner_url:
        raise SystemExit("Set --planner-url and --refiner-url (or env: PLANNER_URL/REFINER_URL).")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    planner_rows = _load_jsonl(Path(args.planner_jsonl))
    refiner_rows = _load_jsonl(Path(args.refiner_jsonl))

    p_map = {r.get("id", "").replace("planner_", ""): r for r in planner_rows}
    r_map = {r.get("id", "").replace("refiner_", ""): r for r in refiner_rows}
    common_ids = sorted(set(p_map) & set(r_map))
    if not common_ids:
        raise SystemExit("No overlapping planner/refiner ids found.")

    rng = random.Random(args.seed)
    indep_ids = rng.sample(common_ids, min(args.n_independent, len(common_ids)))
    remaining = [i for i in common_ids if i not in indep_ids]
    e2e_ids = rng.sample(remaining if remaining else common_ids, min(args.n_e2e, len(common_ids)))

    independent_results: list[dict[str, Any]] = []
    for sid in indep_ids:
        prow = p_map[sid]
        rrow = r_map[sid]
        p_user = _msg(prow["messages"], "user")
        p_gold = _msg(prow["messages"], "assistant")
        r_user = _msg(rrow["messages"], "user")
        r_gold = _msg(rrow["messages"], "assistant")

        p_pred = _post_generate(args.planner_url, p_user, max_tokens=1400, temperature=0.0, timeout_s=args.timeout_s)
        r_pred = _post_generate(args.refiner_url, r_user, max_tokens=2800, temperature=0.0, timeout_s=args.timeout_s)

        rg = _safe_json(r_gold)
        rp = _safe_json(r_pred)
        p_check = _planner_check(p_pred, p_user)
        r_check = _refiner_check(r_pred, planner_text="")
        row = {
            "id": sid,
            "planner_ok": p_check["ok"],
            "planner_score": p_check["score"],
            "planner_errors": p_check["errors"],
            "planner_similarity": round(difflib.SequenceMatcher(None, p_gold, p_pred).ratio(), 4),
            "refiner_json_ok": r_check["ok"],
            "refiner_score": r_check["score"],
            "refiner_errors": r_check["errors"],
            "refiner_gold_json_ok": rg is not None,
        }
        if rp is not None and rg is not None:
            row["refiner_struct_compare"] = _compare_inter(rp, rg)
        independent_results.append(row)

        (out_dir / f"independent_planner_pred_{sid}.txt").write_text(p_pred, encoding="utf-8")
        (out_dir / f"independent_refiner_pred_{sid}.txt").write_text(r_pred, encoding="utf-8")

    e2e_results: list[dict[str, Any]] = []
    for sid in e2e_ids:
        prow = p_map[sid]
        rrow = r_map[sid]
        p_user = _msg(prow["messages"], "user")
        r_user_gold = _msg(rrow["messages"], "user")
        r_gold_txt = _msg(rrow["messages"], "assistant")

        p_pred = _post_generate(args.planner_url, p_user, max_tokens=1400, temperature=0.0, timeout_s=args.timeout_s)
        r_user_e2e = _replace_planner_text(r_user_gold, p_pred)
        r_pred = _post_generate(args.refiner_url, r_user_e2e, max_tokens=2800, temperature=0.0, timeout_s=args.timeout_s)

        r_pred_json = _safe_json(r_pred)
        r_gold_json = _safe_json(r_gold_txt)
        p_check = _planner_check(p_pred, p_user)
        r_check = _refiner_check(r_pred, planner_text=p_pred)
        row = {
            "id": sid,
            "planner_ok": p_check["ok"],
            "planner_score": p_check["score"],
            "planner_errors": p_check["errors"],
            "refiner_json_ok": r_check["ok"],
            "refiner_score": r_check["score"],
            "refiner_errors": r_check["errors"],
            "gold_refiner_json_ok": r_gold_json is not None,
        }
        if r_pred_json is not None and r_gold_json is not None:
            row["inter_compare"] = _compare_inter(r_pred_json, r_gold_json)
            (out_dir / f"e2e_inter_{sid}.json").write_text(
                json.dumps(r_pred_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        e2e_results.append(row)

        (out_dir / f"e2e_planner_pred_{sid}.txt").write_text(p_pred, encoding="utf-8")
        (out_dir / f"e2e_refiner_pred_{sid}.txt").write_text(r_pred, encoding="utf-8")
        (out_dir / f"e2e_refiner_prompt_{sid}.txt").write_text(r_user_e2e, encoding="utf-8")

    report = {
        "planner_url": args.planner_url,
        "refiner_url": args.refiner_url,
        "independent_ids": indep_ids,
        "e2e_ids": e2e_ids,
        "independent_results": independent_results,
        "e2e_results": e2e_results,
        "summary": {
            "independent_planner_ok": f"{sum(1 for r in independent_results if r['planner_ok'])}/{len(independent_results)}",
            "independent_refiner_json_ok": f"{sum(1 for r in independent_results if r['refiner_json_ok'])}/{len(independent_results)}",
            "e2e_planner_ok": f"{sum(1 for r in e2e_results if r['planner_ok'])}/{len(e2e_results)}",
            "e2e_refiner_json_ok": f"{sum(1 for r in e2e_results if r['refiner_json_ok'])}/{len(e2e_results)}",
        },
    }

    out_json = out_dir / "endpoint_eval_report.json"
    out_md = out_dir / "endpoint_eval_report.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Endpoint Eval Report",
        "",
        f"- Planner URL: `{args.planner_url}`",
        f"- Refiner URL: `{args.refiner_url}`",
        f"- Independent IDs: `{', '.join(indep_ids)}`",
        f"- E2E IDs: `{', '.join(e2e_ids)}`",
        "",
        "## Summary",
        "",
        f"- Independent planner format: `{report['summary']['independent_planner_ok']}`",
        f"- Independent refiner JSON: `{report['summary']['independent_refiner_json_ok']}`",
        f"- E2E planner format: `{report['summary']['e2e_planner_ok']}`",
        f"- E2E refiner JSON: `{report['summary']['e2e_refiner_json_ok']}`",
        "",
        "## Files",
        "",
        f"- JSON report: `{out_json}`",
        f"- Per-sample outputs: `{out_dir}`",
    ]
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Saved report: {out_json}")
    print(f"Saved summary: {out_md}")
    print("Summary:", report["summary"])


if __name__ == "__main__":
    main()
