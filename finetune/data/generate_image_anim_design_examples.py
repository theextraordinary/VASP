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

IMAGES_DIR = ROOT / "assets" / "inputs" / "images"
CAPTIONS_CSV = ROOT / "assets" / "inputs" / "captions.txt"
DATA_DIR = ROOT / "finetune" / "data"
OUT_DIR = ROOT / "output"

PLANNER_OUT = DATA_DIR / "planner_image_anim_design_100_examples.jsonl"
REFINER_OUT = DATA_DIR / "refiner_image_anim_design_100_examples.jsonl"
PREVIEW_MD = DATA_DIR / "image_anim_design_100_preview.md"

DEMO_INTER_PREFIX = OUT_DIR / "inter_image_anim_demo_"
DEMO_VIDEO_PREFIX = OUT_DIR / "a2v_video_image_anim_demo_"


STOPWORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "in",
    "on",
    "at",
    "to",
    "of",
    "and",
    "with",
    "for",
    "this",
    "that",
    "there",
    "it",
    "as",
    "by",
    "from",
    "into",
    "over",
    "under",
    "near",
}


@dataclass
class SegmentSpec:
    image_id: str
    image_file: str
    about: str
    aim: str
    start: float
    end: float
    caption_text: str
    highlight_word: str
    x: float
    y: float
    scale: float
    crop_w: float | None
    crop_h: float | None
    crop_x: float
    crop_y: float
    entrance: str
    hold: str


BACKGROUND_STYLES = [
    "clean_black",
    "grain_vignette",
    "cinematic_red",
    "night_blue",
    "morning_energy",
    "mint_daylight",
    "sky_breeze",
    "roman_columns",
    "neutral_dark",
    "map_blue",
    "clean_white",
    "white_pattern",
]

CAPTION_LAYOUTS = [
    ("bottom_center", 540.0, 1585.0),
    ("lower_left", 420.0, 1565.0),
    ("lower_right", 660.0, 1565.0),
    ("mid_lower", 540.0, 1485.0),
]

IMAGE_ANIMS = [
    ("bounce entrance with smooth hold", "bounce", "smooth", "from_bottom"),
    ("slide-up entrance with subtle zoom hold", "slide_up", "smooth", "from_bottom"),
    ("slide-left entrance with slow drift hold", "slide_left", "smooth", "from_right"),
    ("slide-right entrance with slow drift hold", "slide_right", "smooth", "from_left"),
    ("pop entrance with gentle breathe hold", "pop", "smooth", "from_center"),
    ("stomp entrance with stable hold", "pop", "smooth", "from_bottom"),
    ("spin-lite entrance with smooth hold", "elastic", "smooth", "from_center"),
    ("wiggle entrance then settle", "pop", "smooth", "from_left"),
]


def _clean_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" .", ".").replace(" ,", ",")
    return text


def _load_about_map() -> dict[str, list[str]]:
    by_image: dict[str, list[str]] = {}
    with CAPTIONS_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            image = (row.get("image") or "").strip()
            caption = _clean_sentence((row.get("caption") or "").strip())
            if not image or not caption:
                continue
            by_image.setdefault(image, []).append(caption)
    return by_image


def _tokenize(text: str) -> list[str]:
    # Keep punctuation attached for sentence-boundary aware grouping.
    return text.split()


def _pick_highlight_word(text: str) -> str:
    words = [w.strip(".,!?;:()[]{}\"'").lower() for w in _tokenize(text)]
    for w in words:
        if len(w) >= 5 and w not in STOPWORDS:
            return w
    for w in words:
        if w and w not in STOPWORDS:
            return w
    return "focus"


def _build_word_timing_map(words: list[str], start_t: float) -> tuple[list[dict], float]:
    t = start_t
    out: list[dict] = []
    for i, w in enumerate(words):
        dur = random.uniform(0.18, 0.34)
        end_t = t + dur
        out.append({"text": w, "start": round(t, 3), "end": round(end_t, 3)})
        gap = random.uniform(0.035, 0.095)
        if w.endswith((".", "!", "?")):
            gap = random.uniform(0.18, 0.42)
        if i < len(words) - 1 and words[i + 1][:1].isupper():
            gap = max(gap, random.uniform(0.13, 0.22))
        t = end_t + gap
    return out, t


def _compose_sentence(about: str, idx: int) -> str:
    tail = random.choice(
        [
            "This detail anchors the story and keeps the scene easy to follow.",
            "Notice how the visual context matches the narration in this moment.",
            "The next scene will switch only when the caption topic changes.",
            "This is shown clearly so the viewer never loses context.",
            "The framing keeps the focus on this exact topic before the next transition.",
        ]
    )
    lead = random.choice(
        [
            f"In this moment, {about}",
            f"Here we focus on this scene: {about}",
            f"The narration now describes: {about}",
            f"Now the visual topic is: {about}",
        ]
    )
    s = f"{lead}. {tail}"
    # Force sentence boundary diversity.
    if idx % 3 == 0:
        s = f"{lead}. {tail} We cut cleanly to the next image topic after this."
    return _clean_sentence(s)


def _group_words(word_map: list[dict], max_words: int = 5) -> list[list[dict]]:
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for i, w in enumerate(word_map):
        if not cur:
            cur = [w]
            continue
        prev = cur[-1]
        gap = float(w["start"]) - float(prev["end"])
        prev_txt = str(prev["text"])
        cur_txt = str(w["text"])
        long_pause = gap > 0.18
        sentence_cut = prev_txt.endswith((".", "!", "?"))
        uppercase_cut = bool(cur_txt[:1].isupper())
        maxed = len(cur) >= max_words
        if long_pause or sentence_cut or uppercase_cut or maxed:
            groups.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def _safe_font_size(text: str) -> int:
    n = len(text)
    if n <= 18:
        return 62
    if n <= 26:
        return 58
    if n <= 34:
        return 54
    if n <= 44:
        return 50
    return 46


def _entry_from_origin(origin: str, x: float, y: float) -> tuple[float, float]:
    if origin == "from_bottom":
        return x, 2250.0
    if origin == "from_left":
        return -320.0, y
    if origin == "from_right":
        return 1400.0, y
    return x, y + 160.0


def _build_element2_compact(duration: float, segments: list[SegmentSpec], transcript: str, word_map: list[dict]) -> str:
    transcript_clean = transcript.replace("'", "")
    lines: list[str] = [
        "version:1.0",
        f"video:1080x1920 fps=30 output=output/a2v_video.mp4 duration={duration:.3f}",
    ]
    for seg in segments:
        about = seg.about.replace("'", "")
        aim = seg.aim.replace("'", "")
        lines.append(
            f"element:{seg.image_id} type=image source_uri=assets/inputs/images/{seg.image_file} "
            f"timing={seg.start:.3f}-{seg.end:.3f} about='{about}' aim='{aim}'"
        )
    lines.append(
        "element:caption_track_1 type=caption "
        f"timing=0.000-{duration:.3f} transcript='{transcript_clean}' "
        f"word_timing_map={word_map}"
    )
    return "\n".join(lines)


def _build_planner_output(duration: float, bg: str, layout_name: str, segments: list[SegmentSpec]) -> str:
    lines = [
        "EDIT PLAN",
        "Global Style: Clean cinematic visual storytelling with strong image-caption synchronization and non-messy layout.",
        "Audio Decision: No music element is provided; caption timing map is the timeline backbone.",
        "Caption Style: Group captions adaptively 1-5 words, keep text inside 9:16 safe area, highlight only important words.",
        "Visual Style: Show each image exactly when its related caption appears and remove it before next unrelated caption starts.",
        f"Background Style: {bg} with tasteful design layers; avoid clutter.",
        "Segmentation Rule: New segment whenever caption focus changes to a new image topic or sentence boundary.",
    ]
    for i, seg in enumerate(segments, start=1):
        lines.extend(
            [
                f"Segment {i}",
                f"Time: {seg.start:.3f}-{seg.end:.3f}",
                f"Purpose: Present the image topic: {seg.about}",
                f"Elements Used: {seg.image_id}, caption_track_1",
                f"Caption Decision: Show groups from related caption text; important word is '{seg.highlight_word}'.",
                f"Visual Decision: Keep {seg.image_id} visible only during this topic window.",
                f"Animation Decision: Apply {seg.aim}.",
                f"Placement Decision: Caption layout={layout_name}, image around x={seg.x:.0f}, y={seg.y:.0f}, avoid overlap.",
                "Timing Events:",
                f"- time: {seg.start:.3f} event: show {seg.image_id}",
                f"- time: {max(seg.start + 0.25, seg.start):.3f} event: emphasize '{seg.highlight_word}'",
                f"- time: {seg.end:.3f} event: hide {seg.image_id}",
                "Transition Out: Cut cleanly to next caption topic.",
                "Engagement Note: Keep scene simple and readable, never messy.",
            ]
        )
    return "\n".join(lines)


def _build_refiner_inter(duration: float, bg: str, design_events: list[dict], segments: list[SegmentSpec], word_map: list[dict]) -> dict:
    elements: list[dict] = []

    for seg in segments:
        entry_x, entry_y = _entry_from_origin(
            "from_bottom" if seg.entrance in {"bounce", "slide_up", "pop"} else ("from_left" if seg.entrance == "slide_right" else "from_right"),
            seg.x,
            seg.y,
        )
        in_end = min(seg.end, seg.start + 0.45)
        elements.append(
            {
                "element_id": seg.image_id,
                "type": "image",
                "timing": {"start": round(seg.start, 3), "duration": round(seg.end - seg.start, 3)},
                "properties": {
                    "type": "image",
                    "source_uri": f"assets/inputs/images/{seg.image_file}",
                    "timing": {"start": round(seg.start, 3), "duration": round(seg.end - seg.start, 3)},
                    "transform": {"x": seg.x, "y": seg.y},
                },
                "actions": [
                    {
                        "t_start": round(seg.start, 3),
                        "t_end": round(in_end, 3),
                        "op": "show",
                        "params": {
                            "from_x": round(entry_x, 2),
                            "from_y": round(entry_y, 2),
                            "x": seg.x,
                            "y": seg.y,
                            "scale": seg.scale,
                            "motion_ease": seg.entrance if seg.entrance in {"bounce", "pop", "elastic"} else "smooth",
                            "round_corners": 20,
                            "fade_in_s": 0.18,
                            "fade_out_s": 0.16,
                            **(
                                {
                                    "crop_w": seg.crop_w,
                                    "crop_h": seg.crop_h,
                                    "crop_x": seg.crop_x,
                                    "crop_y": seg.crop_y,
                                }
                                if seg.crop_w is not None and seg.crop_h is not None
                                else {}
                            ),
                        },
                    },
                    {
                        "t_start": round(in_end, 3),
                        "t_end": round(seg.end, 3),
                        "op": "show",
                        "params": {
                            "x": seg.x,
                            "y": seg.y,
                            "to_x": seg.x,
                            "to_y": round(max(220.0, seg.y - 18.0), 2),
                            "scale": min(seg.scale + 0.06, seg.scale * 1.08),
                            "motion_ease": "smooth",
                            "round_corners": 20,
                            "fade_in_s": 0.12,
                            "fade_out_s": 0.20,
                            **(
                                {
                                    "crop_w": seg.crop_w,
                                    "crop_h": seg.crop_h,
                                    "crop_x": seg.crop_x,
                                    "crop_y": seg.crop_y,
                                }
                                if seg.crop_w is not None and seg.crop_h is not None
                                else {}
                            ),
                        },
                    },
                ],
            }
        )

    groups = _group_words(word_map, max_words=5)
    caption_actions: list[dict] = []
    for idx, grp in enumerate(groups):
        g_start = float(grp[0]["start"])
        if idx < len(groups) - 1:
            g_end = float(groups[idx + 1][0]["start"])
        else:
            g_end = float(grp[-1]["end"])
        text = " ".join(str(w["text"]) for w in grp)
        important = any(
            str(w["text"]).strip(".,!?;:").lower() in {s.highlight_word for s in segments}
            for w in grp
        )
        fs = _safe_font_size(text) + (4 if important and len(grp) == 1 else 0)
        caption_actions.append(
            {
                "t_start": round(g_start, 3),
                "t_end": round(g_end, 3),
                "op": "show",
                "params": {
                    "text": text,
                    "x": 540.0,
                    "y": 1585.0,
                    "font_size": fs,
                    "font_weight": "bold",
                    "color": "#FFD84D" if (important and len(grp) == 1) else "#FFFFFF",
                    "stroke_color": "#000000",
                    "stroke_width": 3,
                    "background_opacity": 0.20,
                    "background_color": "#000000",
                    "box_border": 12,
                    "caption_placement": "bottom_safe",
                    "caption_animation": random.choice(["word_reveal", "pop", "slide_up", "typewriter"]),
                },
            }
        )

    elements.append(
        {
            "element_id": "caption_track_1",
            "type": "caption",
            "timing": {"start": round(float(word_map[0]["start"]), 3), "duration": round(duration - float(word_map[0]["start"]), 3)},
            "properties": {
                "type": "caption",
                "timing": {"start": round(float(word_map[0]["start"]), 3), "duration": round(duration - float(word_map[0]["start"]), 3)},
                "transform": {"x": 540.0, "y": 1585.0},
                "font_size": 58,
                "font_weight": "bold",
                "color": "#FFFFFF",
                "stroke_color": "#000000",
                "stroke_width": 3,
            },
            "actions": caption_actions,
        }
    )

    return {
        "version": "1.1",
        "video": {
            "size": {"width": 1080, "height": 1920},
            "fps": 30,
            "bg_color": [0, 0, 0],
            "output_path": "output/a2v_video.mp4",
            "background_style": bg,
            "metadata": {"design_events": design_events},
        },
        "properties_path": None,
        "elements": elements,
    }


def _generate_examples(count: int = 100) -> tuple[list[dict], list[dict], list[dict]]:
    random.seed(42)
    about_map = _load_about_map()
    image_files = sorted([p.name for p in IMAGES_DIR.glob("*.jpg") if p.name in about_map])
    if len(image_files) < 6:
        raise RuntimeError("Not enough images with captions found in assets/inputs/images + captions.txt.")

    planner_rows: list[dict] = []
    refiner_rows: list[dict] = []
    demo_payloads: list[dict] = []

    for idx in range(1, count + 1):
        ex_id = f"image_anim_design_{idx:03d}"
        n_images = random.randint(3, 6)
        chosen = random.sample(image_files, n_images)
        bg = random.choice(BACKGROUND_STYLES)
        layout_name, cap_x, cap_y = random.choice(CAPTION_LAYOUTS)
        full_screen_mode = (idx % 5 == 0)

        t = round(random.uniform(0.0, 0.12), 3)
        full_word_map: list[dict] = []
        segments: list[SegmentSpec] = []
        transcript_parts: list[str] = []

        for j, img_name in enumerate(chosen, start=1):
            about = random.choice(about_map[img_name])
            about = _clean_sentence(about)
            anim_label, entrance, hold, _origin = random.choice(IMAGE_ANIMS)
            aim = f"Use {anim_label}; keep image only while related caption is active and remove at next topic."
            sentence = _compose_sentence(about, idx)
            words = _tokenize(sentence)
            seg_start = t
            wm, t = _build_word_timing_map(words, t)
            full_word_map.extend(wm)
            seg_end = t
            t += random.uniform(0.08, 0.22)

            # Keep image region away from lower caption safe area.
            if full_screen_mode:
                x = 540.0
                y = 960.0
                scale = random.choice([4.2, 4.8, 5.4, 6.0])
                crop_w = random.choice([None, 0.92, 0.85])
                crop_h = random.choice([None, 0.92, 0.82])
                crop_x = random.choice([0.02, 0.05, 0.08])
                crop_y = random.choice([0.02, 0.05, 0.08])
            else:
                x = random.choice([260.0, 360.0, 540.0, 720.0, 820.0])
                y = random.choice([460.0, 560.0, 660.0, 760.0, 860.0])
                scale = random.choice([0.95, 1.05, 1.15, 1.25, 1.4, 1.6, 1.8, 2.2])
                crop_w = random.choice([None, 0.90, 0.82, 0.76])
                crop_h = random.choice([None, 0.90, 0.82, 0.76])
                crop_x = random.choice([0.0, 0.03, 0.06, 0.10])
                crop_y = random.choice([0.0, 0.03, 0.06, 0.10])
                if abs(x - cap_x) < 160 and y > 760:
                    y = 620.0

            segments.append(
                SegmentSpec(
                    image_id=f"image_{j}",
                    image_file=img_name,
                    about=about,
                    aim=aim,
                    start=round(seg_start, 3),
                    end=round(seg_end, 3),
                    caption_text=sentence,
                    highlight_word=_pick_highlight_word(about),
                    x=x,
                    y=y,
                    scale=scale,
                    crop_w=crop_w,
                    crop_h=crop_h,
                    crop_x=crop_x,
                    crop_y=crop_y,
                    entrance=entrance,
                    hold=hold,
                )
            )
            transcript_parts.append(sentence)

        if not full_word_map:
            continue

        duration = round(float(full_word_map[-1]["end"]) + 0.15, 3)
        transcript = " ".join(transcript_parts)
        element_compact = _build_element2_compact(duration, segments, transcript, full_word_map)

        user_instruction = (
            "Create a clean high-retention image-caption reel. "
            "When caption text is about an image, that image must appear at that moment, "
            "and it must be removed as soon as the next caption topic starts. "
            "Do not make the video messy."
        )
        planner_prompt = PLANNER_PROMPT_TEMPLATE.format(USER_INSTRUCTION=user_instruction, ELEMENTS=element_compact)
        planner_text = _build_planner_output(duration, bg, layout_name, segments)

        planner_rows.append(
            {
                "task": "planner_edit_plan",
                "id": f"planner_{ex_id}",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are VASP Planner. Return ONLY EDIT PLAN text with exact headings. No JSON. No markdown.",
                    },
                    {"role": "user", "content": planner_prompt},
                    {"role": "assistant", "content": planner_text},
                ],
            }
        )

        # Design events: prefer non-grid styles by default.
        design_events = [
            {
                "type": "panel",
                "t_start": 0.0,
                "t_end": duration,
                "x": "90",
                "y": "1460",
                "w": "iw-180",
                "h": "330",
                "color": random.choice(["#000000", "#111111", "#1a1a1a", "#f3f3f3", "#ffffff"]),
                "opacity": 0.16 if bg not in {"clean_white", "white_pattern"} else 0.11,
            },
            {
                "type": "frame",
                "t_start": 0.0,
                "t_end": duration,
                "color": random.choice(["#FFD84D", "#8EC5FF", "#FFB07C", "#8EF0D2"]),
                "opacity": 0.06,
                "thickness": random.choice([6, 8, 10]),
            },
        ]
        if bg in {"clean_white", "white_pattern"}:
            design_events.append(
                {
                    "type": random.choice(["stripe_h", "stripe_v", "grid"]),
                    "t_start": 0.0,
                    "t_end": duration,
                    "color": random.choice(["#d7d7d7", "#cbd5e1", "#e3d5ca"]),
                    "opacity": 0.08,
                    "cell_w": 220,
                    "cell_h": 220,
                    "thickness": 1,
                    "band_h": 150,
                    "gap_h": 300,
                    "band_w": 140,
                    "gap_w": 320,
                }
            )
        if bg in {"map_blue"}:
            design_events.append(
                {
                    "type": "grid",
                    "t_start": 0.0,
                    "t_end": duration,
                    "cell_w": 180,
                    "cell_h": 180,
                    "thickness": 1,
                    "color": "#84a8ff",
                    "opacity": 0.08,
                }
            )

        inter = _build_refiner_inter(duration, bg, design_events, segments, full_word_map)
        refiner_prompt = build_inter_refiner_prompt(
            user_instruction=user_instruction,
            planner_text=planner_text,
            element_compact_text=element_compact,
        )
        refiner_rows.append(
            {
                "task": "refiner_inter_json",
                "id": f"refiner_{ex_id}",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are VASP Refiner. Return ONLY valid inter.json. Use renderer-supported ops/params only.",
                    },
                    {"role": "user", "content": refiner_prompt},
                    {"role": "assistant", "content": json.dumps(inter, ensure_ascii=False, separators=(",", ":"))},
                ],
            }
        )
        if len(demo_payloads) < 10:
            demo_payloads.append(inter)

    return planner_rows, refiner_rows, demo_payloads


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_preview_md(path: Path, planner_rows: list[dict], refiner_rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    picks = random.sample(range(min(len(planner_rows), len(refiner_rows))), k=min(5, len(planner_rows)))
    out: list[str] = ["# Image Animation/Design Dataset Preview", ""]
    for i, idx in enumerate(picks, start=1):
        p = planner_rows[idx]
        r = refiner_rows[idx]
        out.append(f"## Pair {i}: `{p['id']}` / `{r['id']}`")
        out.append("")
        out.append("### Planner Input (excerpt)")
        out.append("```text")
        out.append(p["messages"][1]["content"][:1500])
        out.append("```")
        out.append("")
        out.append("### Planner Output")
        out.append("```text")
        out.append(p["messages"][2]["content"][:1400])
        out.append("```")
        out.append("")
        out.append("### Refiner Output (excerpt)")
        out.append("```json")
        out.append(r["messages"][2]["content"][:1600])
        out.append("```")
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def _render_demos(demo_payloads: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for i, payload in enumerate(demo_payloads, start=1):
        inter_path = Path(f"{DEMO_INTER_PREFIX}{i}.json")
        video_path = Path(f"{DEMO_VIDEO_PREFIX}{i}.mp4")
        payload = json.loads(json.dumps(payload))
        payload["video"]["output_path"] = str(video_path).replace("\\", "/")
        inter_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        render_from_json(str(inter_path), strict=True)


def main() -> None:
    planner_rows, refiner_rows, demo_payloads = _generate_examples(count=100)
    _write_jsonl(PLANNER_OUT, planner_rows)
    _write_jsonl(REFINER_OUT, refiner_rows)
    _write_preview_md(PREVIEW_MD, planner_rows, refiner_rows)
    _render_demos(demo_payloads)
    print(f"[DONE] planner examples: {len(planner_rows)} -> {PLANNER_OUT}")
    print(f"[DONE] refiner examples: {len(refiner_rows)} -> {REFINER_OUT}")
    print(f"[DONE] preview: {PREVIEW_MD}")
    print("[DONE] rendered 10 demo videos + inter files in output/")


if __name__ == "__main__":
    main()
