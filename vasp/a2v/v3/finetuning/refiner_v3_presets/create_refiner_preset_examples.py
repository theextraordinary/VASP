from __future__ import annotations

import json
from pathlib import Path

from vasp.a2v.v2.refiner_presets_v3 import PRESET_BUNDLES

ROOT = Path(__file__).resolve().parent


TOPICS = [
    ("caption", "", "Nobody expected this moment", "emotional_quote"),
    ("image", "media_2", "the ancient pyramid stood alone", "cinematic_history"),
    ("video", "media_3", "scientists watched the rocket launch", "science_discovery"),
    ("gif", "media_4", "everyone was completely shocked", "comedy_reaction"),
    ("image", "media_5", "breaking news changed the story", "breaking_news"),
    ("video", "media_6", "soldiers returned after the war", "war_documentary"),
    ("image", "media_7", "the galaxy revealed a strange signal", "space_neon"),
    ("caption", "", "the mystery only got darker", "dark_mystery"),
    ("image", "media_8", "the teacher explained the simple idea", "clean_educational"),
    ("gif", "media_9", "the joke landed instantly", "meme_pop"),
]


def _caption_group(i: int, text: str, ts: float) -> dict:
    return {"index": i, "text": text, "start": round(ts, 3), "end": round(ts + 2.2, 3)}


def _input_prompt(i: int, kind: str, media_id: str, text: str, bundle: str) -> str:
    group = _caption_group(i, text, i * 2.4)
    media = {"element_id": media_id, "type": kind, "source_path": f"assets/fake/{media_id}.mp4" if kind in {"video", "gif"} else f"assets/fake/{media_id}.jpg", "about": text, "aim": f"show during '{text}'"} if media_id else {"element_id": "", "type": "", "source_path": "", "about": "", "aim": ""}
    segment = {
        "segment_id": f"segment_{i:03d}",
        "matched_text": text,
        "t_start": group["start"],
        "t_end": group["end"],
        "media_id": media_id,
        "media": media,
        "caption_groups": [group],
        "warnings": ["caption_only_unmatched_from_media_json"] if not media_id else [],
    }
    return "\n\n".join([
        "You are Refiner V3. Choose professional preset names.",
        f"CREATIVITY LEVEL: {4 if i % 3 else 2}",
        f"TARGET BUNDLE HINT: {bundle}",
        "SEGMENT:\n```json\n" + json.dumps(segment, ensure_ascii=False, indent=2) + "\n```",
    ])


def _output_json(i: int, kind: str, media_id: str, text: str, bundle_name: str) -> dict:
    ts = round(i * 2.4, 3)
    te = round(ts + 2.2, 3)
    b = PRESET_BUNDLES[bundle_name]
    caption_layout = "caption_bottom_safe" if media_id else "caption_only_center"
    visual_layout = b["visual_layout_preset"]
    out = {
        "segment_id": f"segment_{i:03d}",
        "creativity_level": 4 if i % 3 else 2,
        "preset_bundle": bundle_name,
        "background_preset": b["background_preset"],
        "caption_preset": b["caption_preset"],
        "caption_layout_preset": caption_layout,
        "visual_layout_preset": visual_layout,
        "caption_animation_preset": b["caption_animation_preset"],
        "visual_animation_preset": b["visual_animation_preset"],
        "transition_preset": b["transition_preset"],
        "t_start": ts,
        "t_end": te,
        "background_timeline": [{"t_start": ts, "t_end": te, "reason": f"preset:{b['background_preset']}"}],
        "caption_timeline": [{
            "caption_group_index": i,
            "text": text,
            "t_start": ts,
            "t_end": te,
            "highlight_words": [],
        }],
        "visual_timeline": [],
        "warnings": [],
    }
    if media_id:
        out["visual_timeline"] = [{
            "element_id": media_id,
            "source_ref": media_id,
            "type": "gif" if kind == "gif" else kind,
            "t_start": ts,
            "t_end": te,
        }]
    return out


def build_examples(count: int = 150) -> list[dict]:
    rows = []
    for i in range(1, count + 1):
        kind, media_id, text, bundle = TOPICS[(i - 1) % len(TOPICS)]
        if i <= 30:
            kind, media_id, bundle = "caption", "", "emotional_quote"
        elif i <= 60:
            kind, media_id = "image", f"media_{i}"
        elif i <= 85:
            kind, media_id = ("gif" if i % 2 else "video"), f"media_{i}"
        prompt = _input_prompt(i, kind, media_id, text, bundle)
        output = _output_json(i, kind, media_id, text, bundle)
        rows.append({"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)}]})
    return rows


def main() -> None:
    rows = build_examples(150)
    out = ROOT / "refiner_v3_preset_150.jsonl"
    pretty = ROOT / "refiner_v3_preset_pretty.json"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    pretty.write_text(json.dumps(rows[:20], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} examples to {out}")


if __name__ == "__main__":
    main()
