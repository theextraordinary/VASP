from __future__ import annotations

import json
import sys
from pathlib import Path

from vasp.a2v.v2.refiner_presets_v3 import (
    ANIMATION_PRESETS,
    BACKGROUND_PRESETS,
    CAPTION_PRESETS,
    LAYOUT_PRESETS,
    PRESET_BUNDLES,
    TRANSITION_PRESETS,
)

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "refiner_v3_preset_150.jsonl"


def _load_segment(prompt: str) -> dict:
    start = prompt.find("{")
    end = prompt.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        return json.loads(prompt[start : end + 1])
    except Exception:
        return {}


def _inside(layout: dict) -> bool:
    x = float(layout.get("x", 0))
    y = float(layout.get("y", 0))
    w = float(layout.get("width", 0))
    h = float(layout.get("height", 0))
    return x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1080 and y + h <= 1920


def validate_row(row: dict, line_no: int) -> list[str]:
    errs: list[str] = []
    msgs = row.get("messages")
    if not isinstance(msgs, list) or len(msgs) != 2:
        return [f"{line_no}: messages invalid"]
    seg = _load_segment(str(msgs[0].get("content", "")))
    try:
        out = json.loads(str(msgs[1].get("content", "")))
    except Exception:
        return [f"{line_no}: assistant output invalid json"]
    for key in ("segment_id", "t_start", "t_end", "caption_timeline", "visual_timeline", "background_timeline"):
        if key not in out:
            errs.append(f"{line_no}: missing {key}")
    checks = [
        ("preset_bundle", PRESET_BUNDLES),
        ("background_preset", BACKGROUND_PRESETS),
        ("caption_preset", CAPTION_PRESETS),
        ("caption_layout_preset", LAYOUT_PRESETS),
        ("visual_layout_preset", LAYOUT_PRESETS),
        ("caption_animation_preset", ANIMATION_PRESETS),
        ("visual_animation_preset", ANIMATION_PRESETS),
        ("transition_preset", TRANSITION_PRESETS),
    ]
    for key, table in checks:
        val = out.get(key)
        if val and val not in table:
            errs.append(f"{line_no}: unknown {key}={val}")
    if abs(float(out.get("t_start", -1)) - float(seg.get("t_start", -2))) > 1e-3:
        errs.append(f"{line_no}: t_start changed")
    if abs(float(out.get("t_end", -1)) - float(seg.get("t_end", -2))) > 1e-3:
        errs.append(f"{line_no}: t_end changed")
    media_id = str(seg.get("media_id") or "")
    visuals = out.get("visual_timeline") if isinstance(out.get("visual_timeline"), list) else []
    if not media_id and visuals:
        errs.append(f"{line_no}: caption-only has visual")
    if media_id:
        if len(visuals) != 1:
            errs.append(f"{line_no}: visual segment should have one visual")
        elif visuals[0].get("element_id") != media_id:
            errs.append(f"{line_no}: media_id not preserved")
    captions = out.get("caption_timeline") if isinstance(out.get("caption_timeline"), list) else []
    if len(captions) < len(seg.get("caption_groups") or []):
        errs.append(f"{line_no}: captions do not cover groups")
    layout_name = out.get("caption_layout_preset")
    if layout_name and not _inside(LAYOUT_PRESETS[layout_name]):
        errs.append(f"{line_no}: caption layout outside canvas")
    v_layout_name = out.get("visual_layout_preset")
    if v_layout_name and not _inside(LAYOUT_PRESETS[v_layout_name]):
        errs.append(f"{line_no}: visual layout outside canvas")
    return errs


def main() -> None:
    errs: list[str] = []
    if not DATASET.exists():
        errs.append(f"dataset missing: {DATASET}")
    else:
        for i, line in enumerate(DATASET.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                errs.extend(validate_row(json.loads(line), i))
    report = {"ok": not errs, "errors": errs, "error_count": len(errs)}
    (ROOT / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if errs:
        sys.exit(1)


if __name__ == "__main__":
    main()
