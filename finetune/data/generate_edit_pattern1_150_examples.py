from __future__ import annotations

import csv
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vasp.a2v.main import PLANNER_PROMPT_TEMPLATE
from vasp.refiner.prompt_templates import build_inter_refiner_prompt
from vasp.render.element_renderer import render_from_json


DATA_DIR = ROOT / "finetune" / "data"
OUT_DIR = ROOT / "output"
IMAGES_DIR = ROOT / "assets" / "inputs" / "images"
CAPTION_CSV = ROOT / "assets" / "inputs" / "captions.txt"
SONG_MAPS = DATA_DIR / "song_word_maps.json"

PLANNER_FILE = DATA_DIR / "planner_edit_pattern1_150_examples.jsonl"
REFINER_FILE = DATA_DIR / "refiner_edit_pattern1_150_examples.jsonl"
PREVIEW_FILE = DATA_DIR / "edit_pattern1_150_preview.md"


@dataclass
class ImageSlot:
    element_id: str
    file_name: str
    about: str
    aim: str
    start: float
    end: float
    mention: str
    x: float
    y: float
    scale: float


THEMES = [
    {
        "name": "warm_clean",
        "bg": "morning_energy",
        "event_color": "#ffd2a6",
        "caption_color": "#FFFFFF",
        "important_color": "#ffbe3d",
        "image_anim": "slide_up",
        "caption_anim": "word_reveal",
    },
    {
        "name": "dark_cinematic",
        "bg": "grain_vignette",
        "event_color": "#111111",
        "caption_color": "#FFFFFF",
        "important_color": "#FFD84D",
        "image_anim": "pop",
        "caption_anim": "pop",
    },
    {
        "name": "clean_white",
        "bg": "clean_white",
        "event_color": "#f2f2f2",
        "caption_color": "#0f172a",
        "important_color": "#0ea5e9",
        "image_anim": "slide_left",
        "caption_anim": "slide_up",
    },
    {
        "name": "white_pattern",
        "bg": "white_pattern",
        "event_color": "#e7e7e7",
        "caption_color": "#111827",
        "important_color": "#ef4444",
        "image_anim": "slide_right",
        "caption_anim": "typewriter",
    },
    {
        "name": "blue_night",
        "bg": "night_blue",
        "event_color": "#0e1e3a",
        "caption_color": "#FFFFFF",
        "important_color": "#8EC5FF",
        "image_anim": "bounce",
        "caption_anim": "word_reveal",
    },
]


STOP = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "in",
    "on",
    "of",
    "and",
    "with",
    "to",
    "for",
    "this",
    "that",
    "there",
    "it",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().replace(" .", ".").replace(" ,", ",")


def _tok(text: str) -> list[str]:
    return text.split()


def _important_word(text: str) -> str:
    for w in _tok(text):
        t = w.strip(".,!?;:'\"").lower()
        if len(t) >= 5 and t not in STOP:
            return t
    for w in _tok(text):
        t = w.strip(".,!?;:'\"").lower()
        if t and t not in STOP:
            return t
    return "focus"


def _load_about_map() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with CAPTION_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            img = (row.get("image") or "").strip()
            cap = _clean((row.get("caption") or "").strip())
            if img and cap:
                out.setdefault(img, []).append(cap)
    return out


def _load_song_maps() -> list[dict]:
    arr = json.loads(SONG_MAPS.read_text(encoding="utf-8"))
    return [x for x in arr if isinstance(x, dict) and x.get("audio_path") and isinstance(x.get("word_timing_map"), list)]


def _make_synthetic_words(slots: list[ImageSlot], start: float = 0.0) -> list[dict]:
    words: list[dict] = []
    t = start
    for i, s in enumerate(slots, start=1):
        sentence = _clean(
            f"We keep the edit simple and clean while showing this scene: {s.about}. "
            f"As this caption talks about {s.mention}, the related image appears clearly and then exits for the next topic."
        )
        for w in _tok(sentence):
            dur = random.uniform(0.16, 0.30)
            words.append({"text": w, "start": round(t, 3), "end": round(t + dur, 3)})
            gap = random.uniform(0.03, 0.08)
            if w.endswith((".", "!", "?")):
                gap = random.uniform(0.16, 0.28)
            t += dur + gap
        if i < len(slots):
            t += random.uniform(0.10, 0.18)
    return words


def _build_slots(image_choices: list[tuple[str, str]], start: float, end: float) -> list[ImageSlot]:
    n = len(image_choices)
    total = max(8.0, end - start)
    seg = total / n
    slots: list[ImageSlot] = []
    for i, (img_file, about) in enumerate(image_choices, start=1):
        st = start + (i - 1) * seg
        en = start + i * seg
        mention = _important_word(about)
        slots.append(
            ImageSlot(
                element_id=f"image_{i}",
                file_name=img_file,
                about=about,
                aim="Cover frame horizontally when mentioned, then fade out as next topic starts.",
                start=round(st, 3),
                end=round(en, 3),
                mention=mention,
                x=540.0,
                y=random.choice([760.0, 820.0, 900.0]),
                scale=random.choice([2.2, 2.5, 2.8, 3.1]),
            )
        )
    return slots


def _song_anchor_mentions(words: list[dict], n: int) -> list[str]:
    if not words or n <= 0:
        return []
    picks: list[str] = []
    for i in range(n):
        pos = min(len(words) - 1, int((i + 0.5) * len(words) / n))
        token = str(words[pos]["text"]).strip(".,!?;:'\"").lower()
        if not token:
            token = "moment"
        picks.append(token)
    return picks


def _group_words(words: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if not cur:
            cur = [w]
            continue
        prev = cur[-1]
        gap = float(w["start"]) - float(prev["end"])
        cut = (
            gap > 0.18
            or str(prev["text"]).endswith((".", "!", "?"))
            or str(w["text"])[:1].isupper()
            or len(cur) >= 5
        )
        if cut:
            groups.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def _element_compact(audio_path: str, duration: float, slots: list[ImageSlot], words: list[dict], transcript: str) -> str:
    transcript_clean = transcript.replace("'", "")
    lines = [
        "version:1.0",
        f"video:1080x1920 fps=30 output=output/a2v_video.mp4 duration={duration:.3f}",
        f"element:audio_1 type=music source_uri={audio_path} timing=0.000-{duration:.3f}",
    ]
    for s in slots:
        about_clean = s.about.replace("'", "")
        lines.append(
            f"element:{s.element_id} type=image source_uri=assets/inputs/images/{s.file_name} "
            f"timing={s.start:.3f}-{s.end:.3f} about='{about_clean}' aim='{s.aim}'"
        )
    lines.append(
        "element:caption_track_1 type=caption "
        f"timing=0.000-{duration:.3f} transcript='{transcript_clean}' "
        f"word_timing_map={words}"
    )
    return "\n".join(lines)


def _planner_output(theme: dict, duration: float, slots: list[ImageSlot], mode: str) -> str:
    lines = [
        "EDIT PLAN",
        "Global Style: Simple clean high-retention edit with no empty screen and consistent visual language.",
        f"Audio Decision: Use audio_1 from 0.000-{duration:.3f} as {'song+captions' if mode=='song_whisper' else 'background bed with authored captions'}.",
        f"Caption Style: Large readable captions with key-word highlight color {theme['important_color']}, always visible in safe lower zone.",
        "Visual Style: When an image topic is captioned, image expands horizontally and captions shift lower; image fades out before next topic.",
        f"Background Style: {theme['bg']} with minimal pattern and clean contrast.",
        "Segmentation Rule: Split by sentence/topic change; keep continuity so screen never feels empty.",
    ]
    for i, s in enumerate(slots, start=1):
        lines += [
            f"Segment {i}",
            f"Time: {s.start:.3f}-{s.end:.3f}",
            f"Purpose: Highlight image topic: {s.about}",
            f"Elements Used: audio_1, {s.element_id}, caption_track_1",
            f"Caption Decision: Caption explicitly mentions '{s.mention}' while this image is active.",
            f"Visual Decision: {s.element_id} covers horizontal frame, then exits on next topic.",
            f"Animation Decision: {theme['image_anim']} in, smooth hold, fade out.",
            "Placement Decision: Image center-upper; captions bottom safe area.",
            "Timing Events:",
            f"- time: {s.start:.3f} event: show {s.element_id}",
            f"- time: {s.end-0.20:.3f} event: fade out {s.element_id}",
            f"- time: {s.end:.3f} event: next caption/image topic starts",
            "Transition Out: Soft crossfade to next topic block.",
            "Engagement Note: Keep pacing catchy while preserving clean readability.",
        ]
    return "\n".join(lines)


def _build_inter(theme: dict, duration: float, audio_path: str, slots: list[ImageSlot], words: list[dict]) -> dict:
    groups = _group_words(words)
    highlights = {s.mention for s in slots}

    elements = [
        {
            "element_id": "audio_1",
            "type": "music",
            "timing": {"start": 0.0, "duration": round(duration, 3)},
            "properties": {"type": "music", "source_uri": audio_path, "timing": {"start": 0.0, "duration": round(duration, 3)}},
            "actions": [
                {"t_start": 0.0, "t_end": round(duration / 2, 3), "op": "play", "params": {"volume": 1.0}},
                {"t_start": round(duration / 2, 3), "t_end": round(duration, 3), "op": "play", "params": {"volume": 1.0}},
            ],
        }
    ]

    for s in slots:
        enter_end = min(s.end, s.start + 0.45)
        elements.append(
            {
                "element_id": s.element_id,
                "type": "image",
                "timing": {"start": s.start, "duration": round(s.end - s.start, 3)},
                "properties": {
                    "type": "image",
                    "source_uri": f"assets/inputs/images/{s.file_name}",
                    "timing": {"start": s.start, "duration": round(s.end - s.start, 3)},
                    "transform": {"x": s.x, "y": s.y},
                },
                "actions": [
                    {
                        "t_start": s.start,
                        "t_end": round(enter_end, 3),
                        "op": "show",
                        "params": {
                            "from_x": s.x,
                            "from_y": 2200.0 if theme["image_anim"] in {"slide_up", "bounce", "pop"} else s.y,
                            "x": s.x,
                            "y": s.y,
                            "scale": s.scale,
                            "motion_ease": "bounce" if theme["image_anim"] in {"bounce", "pop"} else "smooth",
                            "fade_in_s": 0.18,
                            "fade_out_s": 0.12,
                            "crop_w": random.choice([0.92, 0.85, 0.78]),
                            "crop_h": random.choice([0.92, 0.85, 0.78]),
                            "crop_x": random.choice([0.0, 0.03, 0.06]),
                            "crop_y": random.choice([0.0, 0.03, 0.06]),
                            "round_corners": 16,
                        },
                    },
                    {
                        "t_start": round(enter_end, 3),
                        "t_end": s.end,
                        "op": "show",
                        "params": {
                            "x": s.x,
                            "y": s.y,
                            "to_x": s.x,
                            "to_y": max(420.0, s.y - 16.0),
                            "scale": min(4.0, s.scale + 0.08),
                            "motion_ease": "smooth",
                            "fade_in_s": 0.10,
                            "fade_out_s": 0.22,
                            "crop_w": random.choice([0.92, 0.85, 0.78]),
                            "crop_h": random.choice([0.92, 0.85, 0.78]),
                            "crop_x": random.choice([0.0, 0.03, 0.06]),
                            "crop_y": random.choice([0.0, 0.03, 0.06]),
                            "round_corners": 16,
                        },
                    },
                ],
            }
        )

    cap_actions = []
    for i, g in enumerate(groups):
        st = float(g[0]["start"])
        en = float(groups[i + 1][0]["start"]) if i < len(groups) - 1 else float(g[-1]["end"])
        text = " ".join(str(x["text"]) for x in g)
        imp = any(str(x["text"]).strip(".,!?;:'\"").lower() in highlights for x in g)
        fs = 62 if len(text) <= 22 else 58 if len(text) <= 30 else 54
        cap_actions.append(
            {
                "t_start": round(st, 3),
                "t_end": round(en, 3),
                "op": "show",
                "params": {
                    "text": text,
                    "x": 540.0,
                    "y": 1620.0,
                    "font_size": fs,
                    "font_weight": "bold",
                    "color": theme["important_color"] if imp and len(g) <= 2 else theme["caption_color"],
                    "stroke_color": "#000000",
                    "stroke_width": 3,
                    "background_opacity": 0.20 if theme["bg"] not in {"clean_white", "white_pattern"} else 0.08,
                    "background_color": "#000000" if theme["bg"] not in {"clean_white", "white_pattern"} else "#ffffff",
                    "box_border": 12,
                    "caption_placement": "bottom_safe",
                    "caption_animation": theme["caption_anim"],
                },
            }
        )

    elements.append(
        {
            "element_id": "caption_track_1",
            "type": "caption",
            "timing": {"start": round(float(words[0]["start"]), 3), "duration": round(duration - float(words[0]["start"]), 3)},
            "properties": {
                "type": "caption",
                "timing": {"start": round(float(words[0]["start"]), 3), "duration": round(duration - float(words[0]["start"]), 3)},
                "transform": {"x": 540.0, "y": 1620.0},
                "font_size": 58,
                "font_weight": "bold",
                "color": theme["caption_color"],
                "stroke_color": "#000000",
                "stroke_width": 3,
            },
            "actions": cap_actions,
        }
    )

    design_events = [
        {
            "type": "panel",
            "t_start": 0.0,
            "t_end": round(duration, 3),
            "x": "70",
            "y": "1460",
            "w": "iw-140",
            "h": "360",
            "color": theme["event_color"],
            "opacity": 0.12 if theme["bg"] in {"clean_white", "white_pattern"} else 0.18,
        },
        {"type": "frame", "t_start": 0.0, "t_end": round(duration, 3), "color": theme["important_color"], "opacity": 0.06, "thickness": 8},
    ]
    if theme["bg"] == "white_pattern":
        design_events.append({"type": "stripe_h", "t_start": 0.0, "t_end": round(duration, 3), "color": "#d2d6dc", "opacity": 0.07, "band_h": 140, "gap_h": 310})

    return {
        "version": "1.1",
        "video": {
            "size": {"width": 1080, "height": 1920},
            "fps": 30,
            "bg_color": [0, 0, 0],
            "output_path": "output/a2v_video.mp4",
            "background_style": theme["bg"],
            "metadata": {"design_events": design_events},
        },
        "properties_path": None,
        "elements": elements,
    }


def _pick_images(about_map: dict[str, list[str]], count: int) -> list[tuple[str, str]]:
    files = [f for f in sorted((IMAGES_DIR).glob("*.jpg")) if f.name in about_map]
    chosen = random.sample(files, count)
    out: list[tuple[str, str]] = []
    for p in chosen:
        out.append((p.name, random.choice(about_map[p.name])))
    return out


def _song_words(song_item: dict, max_words: int = 65) -> list[dict]:
    words = song_item.get("word_timing_map") or []
    words = [w for w in words if isinstance(w, dict) and w.get("text") is not None]
    if not words:
        return []
    words = words[:max_words]
    off = float(words[0]["start"])
    out = []
    for w in words:
        st = max(0.0, float(w["start"]) - off)
        en = max(st + 0.05, float(w["end"]) - off)
        out.append({"text": str(w["text"]), "start": round(st, 3), "end": round(en, 3)})
    return out


def _merge_rows(target: Path, extra_rows: list[dict]) -> int:
    rows: list[dict] = []
    if target.exists():
        with target.open("r", encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    by_id = {r.get("id"): r for r in rows if r.get("id") is not None}
    no_id = [r for r in rows if r.get("id") is None]
    for r in extra_rows:
        rid = r.get("id")
        if rid is None:
            no_id.append(r)
        else:
            by_id[rid] = r
    merged = no_id + list(by_id.values())
    merged.sort(key=lambda x: str(x.get("id", "")))
    with target.open("w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(merged)


def main() -> None:
    random.seed(20260421)
    about_map = _load_about_map()
    song_maps = _load_song_maps()
    planner_rows: list[dict] = []
    refiner_rows: list[dict] = []

    for i in range(1, 151):
        theme = random.choice(THEMES)
        n_images = random.randint(2, 3)
        image_choices = _pick_images(about_map, n_images)

        mode = "song_whisper"
        words: list[dict]
        audio_path: str
        song_item = random.choice(song_maps)
        audio_path = str(song_item["audio_path"])
        words = _song_words(song_item, max_words=random.randint(55, 90))
        if len(words) < 24:
            # fallback: pick another song map with richer captions
            dense = [s for s in song_maps if len(s.get("word_timing_map") or []) >= 24]
            song_item = random.choice(dense) if dense else song_item
            audio_path = str(song_item["audio_path"])
            words = _song_words(song_item, max_words=random.randint(55, 90))

        if not words:
            continue

        duration = round(float(words[-1]["end"]) + 0.20, 3)
        slots = _build_slots(image_choices, float(words[0]["start"]), duration)
        # Keep strict song-caption sync: do NOT rewrite word timings.
        anchors = _song_anchor_mentions(words, len(slots))
        for j, s in enumerate(slots):
            if j < len(anchors) and anchors[j]:
                s.mention = anchors[j]

        transcript = " ".join(str(w["text"]) for w in words)
        element_compact = _element_compact(audio_path, duration, slots, words, transcript)
        pattern_instruction = (
            "Edit Pattern 1: no empty screen; large captions should always carry the scene. "
            "When image is needed, image should cover screen horizontally and caption shifts lower. "
            "As image exits, next caption or next image should immediately continue. "
            "Keep style consistent, simple, clean, catchy, and engaging."
        )
        user_instruction = (
            f"{pattern_instruction} Use song audio_1 with whisper captions; keep caption-to-audio sync exact."
        )
        planner_prompt = PLANNER_PROMPT_TEMPLATE.format(USER_INSTRUCTION=user_instruction, ELEMENTS=element_compact)
        planner_text = _planner_output(theme, duration, slots, mode)

        planner_rows.append(
            {
                "task": "planner_edit_plan",
                "id": f"planner_edit_pattern1_{i:03d}",
                "messages": [
                    {"role": "system", "content": "You are VASP Planner. Return ONLY EDIT PLAN text with exact headings. No JSON. No markdown."},
                    {"role": "user", "content": planner_prompt},
                    {"role": "assistant", "content": planner_text},
                ],
            }
        )

        inter = _build_inter(theme, duration, audio_path, slots, words)
        refiner_prompt = build_inter_refiner_prompt(
            user_instruction=user_instruction,
            planner_text=planner_text,
            element_compact_text=element_compact,
        )
        refiner_rows.append(
            {
                "task": "refiner_inter_json",
                "id": f"refiner_edit_pattern1_{i:03d}",
                "messages": [
                    {"role": "system", "content": "You are VASP Refiner. Return ONLY valid inter.json. Use renderer-supported ops/params only."},
                    {"role": "user", "content": refiner_prompt},
                    {"role": "assistant", "content": json.dumps(inter, ensure_ascii=False, separators=(",", ":"))},
                ],
            }
        )

    # write dedicated files
    with PLANNER_FILE.open("w", encoding="utf-8") as f:
        for r in planner_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with REFINER_FILE.open("w", encoding="utf-8") as f:
        for r in refiner_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # append to master paired sets
    planner_total = _merge_rows(DATA_DIR / "planner_train_paired.jsonl", planner_rows)
    refiner_total = _merge_rows(DATA_DIR / "refiner_train_paired.jsonl", refiner_rows)

    # preview md
    picks = random.sample(range(len(planner_rows)), k=min(5, len(planner_rows)))
    md = ["# Edit Pattern 1 - 150 Examples Preview", ""]
    for k, idx in enumerate(picks, start=1):
        p = planner_rows[idx]
        r = refiner_rows[idx]
        md += [
            f"## Pair {k}: {p['id']}",
            "",
            "### Planner Output",
            "```text",
            p["messages"][2]["content"][:1600],
            "```",
            "",
            "### Refiner Output (excerpt)",
            "```json",
            r["messages"][2]["content"][:1800],
            "```",
            "",
        ]
    PREVIEW_FILE.write_text("\n".join(md), encoding="utf-8")

    # render first 5 demos
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(1, 6):
        row = refiner_rows[i - 1]
        inter = json.loads(row["messages"][2]["content"])
        inter_path = OUT_DIR / f"inter_edit_pattern1_demo_{i}.json"
        video_path = OUT_DIR / f"a2v_video_edit_pattern1_demo_{i}.mp4"
        inter["video"]["output_path"] = str(video_path).replace("\\", "/")
        inter_path.write_text(json.dumps(inter, indent=2), encoding="utf-8")
        render_from_json(str(inter_path), strict=True)

    print(f"[DONE] planner examples: {len(planner_rows)} -> {PLANNER_FILE}")
    print(f"[DONE] refiner examples: {len(refiner_rows)} -> {REFINER_FILE}")
    print(f"[DONE] preview -> {PREVIEW_FILE}")
    print(f"[DONE] total paired counts -> planner:{planner_total} refiner:{refiner_total}")
    print("[DONE] rendered 5 demos -> output/inter_edit_pattern1_demo_*.json + output/a2v_video_edit_pattern1_demo_*.mp4")


if __name__ == "__main__":
    main()
