from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REFINER_LAYOUT_SYSTEM_PROMPT = """You are a precise video layout and timing planner.

Your job:
Convert the high-level edit plan into exact renderer placement instructions.

You receive:
1. video canvas info
2. media elements with type, duration, size, about, aim
3. transcript word/phrase timing
4. high-level edit plan from Planner LLM

You must output exact time-accurate element actions.

Rules:
- Return ONLY valid JSON.
- Do not explain.
- Do not copy the input.
- Do not invent media IDs.
- Use the transcript timing to choose exact timestamps.
- Captions must always stay readable and synced.
- Visuals must never cover captions.
- Elements must stay inside canvas.
- Only one main full-screen visual should be active at a time.
- GIFs/stickers are accents, not full-screen backgrounds.
- Audio has no x/y/width/height.
- Use z_index carefully:
  - background visual: 1
  - supporting sticker/gif: 3
  - caption background/panel: 8
  - caption text: 10
- For vertical 1080x1920 video:
  - main visual safe area: x=0, y=0, width=1080, height=1450
  - caption safe area: x=90, y=1450, width=900, height=300
  - sticker/gif accent zones: top-left, top-right, mid-left, mid-right
- Do not place important visual content behind captions.
- If a segment says "transitioning to", split the segment into two or more exact subsegments.
- If media is only supporting, show it briefly for 1.0 to 2.5 seconds.
- Use fade/zoom/cut transitions where appropriate.
- Keep timing smooth and continuous.
"""


REFINER_LAYOUT_OUTPUT_SCHEMA = """{
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "duration": 30.035
  },
  "final_timeline": [
    {
      "element_id": "string",
      "type": "audio | video | image | gif | sticker | caption",
      "role": "main_audio | main_visual | supporting_visual | accent | caption",
      "t_start": number,
      "t_end": number,
      "x": number,
      "y": number,
      "width": number,
      "height": number,
      "z_index": number,
      "opacity": number,
      "fit": "cover | contain | none",
      "transition_in": {
        "type": "none | fade | cut | zoom | slide | pop",
        "duration": number
      },
      "transition_out": {
        "type": "none | fade | cut | zoom | slide | pop",
        "duration": number
      },
      "animation": {
        "type": "none | slow_zoom_in | slow_zoom_out | float | pulse | shake",
        "intensity": "low | medium | high"
      },
      "caption_safe": true,
      "reason": "short reason"
    }
  ],
  "caption_plan": {
    "element_id": "caption_track_1",
    "mode": "phrase_synced",
    "placement": {
      "x": 90,
      "y": 1450,
      "width": 900,
      "height": 300,
      "z_index": 10
    },
    "sync_source": "word_timing_map",
    "style_notes": "large readable captions with highlighted spoken phrase"
  },
  "warnings": []
}"""


def build_refiner_layout_input_prompt(
    *,
    planner_output_text: str,
    media_json: dict[str, Any],
) -> str:
    caption_map = _extract_caption_time_mapping(media_json)
    canvas = _extract_canvas(media_json)
    duration = _extract_duration(media_json)
    elements = _extract_elements_compact(media_json)

    user_block = {
        "canvas": canvas,
        "duration": duration,
        "elements": elements,
        "caption_time_mapping": caption_map,
        "planner_output": planner_output_text.strip(),
    }

    return (
        f"{REFINER_LAYOUT_SYSTEM_PROMPT}\n"
        "Input:\n"
        f"{json.dumps(user_block, ensure_ascii=False, indent=2)}\n\n"
        "Output schema:\n"
        f"{REFINER_LAYOUT_OUTPUT_SCHEMA}\n"
    )


def write_refiner_layout_input_prompt(
    *,
    planner_output_path: str | Path,
    media_json_path: str | Path = "output/media.json",
    output_prompt_path: str | Path = "output/refiner_layout_input_prompt.txt",
) -> Path:
    planner_path = Path(planner_output_path)
    media_path = Path(media_json_path)
    out_path = Path(output_prompt_path)

    if not planner_path.exists():
        raise FileNotFoundError(f"Planner output file not found: {planner_path}")
    if not media_path.exists():
        raise FileNotFoundError(f"media.json file not found: {media_path}")

    planner_text = planner_path.read_text(encoding="utf-8")
    media_json = json.loads(media_path.read_text(encoding="utf-8"))
    prompt = build_refiner_layout_input_prompt(planner_output_text=planner_text, media_json=media_json)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(prompt, encoding="utf-8")
    return out_path


def _extract_caption_time_mapping(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = ((media_json.get("media_context") or {}).get("analysis") or {})
    if not isinstance(analysis, dict):
        return []
    for block in analysis.values():
        if not isinstance(block, dict):
            continue
        transcript = block.get("transcript")
        if not isinstance(transcript, dict):
            continue
        groups = transcript.get("caption_groups")
        if isinstance(groups, list) and groups:
            out: list[dict[str, Any]] = []
            for i, g in enumerate(groups):
                if not isinstance(g, dict):
                    continue
                out.append(
                    {
                        "index": i,
                        "text": str(g.get("text", "")).strip(),
                        "start": _rf(g.get("start"), 0.0),
                        "end": _rf(g.get("end"), 0.0),
                    }
                )
            if out:
                return out
    return []


def _extract_canvas(media_json: dict[str, Any]) -> dict[str, Any]:
    video = media_json.get("video", {}) if isinstance(media_json, dict) else {}
    size = video.get("size", {}) if isinstance(video, dict) else {}
    return {
        "width": int(float(size.get("width", 1080) or 1080)),
        "height": int(float(size.get("height", 1920) or 1920)),
        "fps": int(float(video.get("fps", 30) or 30)),
    }


def _extract_duration(media_json: dict[str, Any]) -> float:
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    max_dur = 0.0
    if isinstance(probe, dict):
        for p in probe.values():
            if not isinstance(p, dict):
                continue
            max_dur = max(max_dur, float(p.get("duration") or 0.0))
    return round(max_dur, 3) if max_dur > 0 else 30.0


def _extract_elements_compact(media_json: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = ((media_json.get("media_context") or {}).get("inputs") or [])
    probe = ((media_json.get("media_context") or {}).get("probe") or {})
    out: list[dict[str, Any]] = []
    if not isinstance(inputs, list):
        return out
    for item in inputs:
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("id", "")).strip()
        p = probe.get(media_id, {}) if isinstance(probe, dict) else {}
        out.append(
            {
                "element_id": media_id,
                "type": item.get("media_type"),
                "duration": _rf(p.get("duration"), 0.0),
                "width": _rf(p.get("width"), 0.0),
                "height": _rf(p.get("height"), 0.0),
                "about": item.get("about"),
                "aim": item.get("aim"),
            }
        )
    return out


def _rf(v: Any, default: float) -> float:
    try:
        return round(float(v), 3)
    except Exception:
        return default


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build refiner input prompt from planner output + caption time mapping from media.json."
    )
    parser.add_argument("--planner-output", required=True, help="Path to planner output text file.")
    parser.add_argument("--media-json", default="output/media.json")
    parser.add_argument("--output", default="output/refiner_layout_input_prompt.txt")
    args = parser.parse_args()

    out = write_refiner_layout_input_prompt(
        planner_output_path=args.planner_output,
        media_json_path=args.media_json,
        output_prompt_path=args.output,
    )
    print(out)


if __name__ == "__main__":
    main()
