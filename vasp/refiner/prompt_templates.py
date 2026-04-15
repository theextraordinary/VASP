from __future__ import annotations

import json

from vasp.animation.catalog import list_animation_presets
from vasp.assets.semantic_library import (
    list_semantic_gif_keys,
    list_semantic_sfx_keys,
    list_semantic_sticker_keys,
)
from vasp.design.render_catalog import render_design_catalog_text


INTER_SCHEMA_GUIDE = {
    "version": "1.1",
    "video": {
        "size": {"width": 1080, "height": 1920},
        "fps": 30,
        "bg_color": [0, 0, 0],
        "output_path": "output/a2v_video.mp4",
        "background_style": "grain_vignette",
    },
    "properties_path": None,
    "elements": [
        {
            "element_id": "caption_track_1",
            "type": "caption",
            "timing": {"start": 0.0, "duration": 10.0},
            "properties": {
                "type": "caption",
                "timing": {"start": 0.0, "duration": 10.0},
                "transform": {"x": 540.0, "y": 1570.0},
                "font_size": 62,
                "font_weight": "bold",
                "color": "#FFFFFF",
                "stroke_color": "#000000",
                "stroke_width": 3,
            },
            "actions": [
                {
                    "t_start": 0.0,
                    "t_end": 1.2,
                    "op": "show",
                    "params": {"text": "example caption group", "x": 540.0, "y": 1570.0, "font_size": 62},
                }
            ],
        }
    ],
}


def build_inter_refiner_prompt(
    *,
    user_instruction: str,
    planner_text: str,
    element_compact_text: str,
) -> str:
    animations = ", ".join(list_animation_presets())
    sfx_keys = ", ".join(list_semantic_sfx_keys())
    gif_keys = ", ".join(list_semantic_gif_keys())
    sticker_keys = ", ".join(list_semantic_sticker_keys())
    design_catalog = render_design_catalog_text()
    schema_json = json.dumps(INTER_SCHEMA_GUIDE, indent=2)

    return (
        "You are VASP Refiner. Convert planner text into strict renderer-ready inter.json.\n"
        "Return ONLY valid JSON object (no markdown, no prose).\n\n"
        "HARD RULES:\n"
        "1) Keep only renderer-useful fields. Avoid unnecessary metadata unless used by actions.\n"
        "2) Use element_id/type/source_uri from ELEMENT_COMPACT only. Never invent file paths.\n"
        "3) Use op='play' for music/sfx and op='show' for visual/caption elements.\n"
        "4) For captions, keep base text white and highlight ONLY important words; never tint full sentence blocks.\n"
        "5) Keep caption sizes stable and 9:16 safe (avoid overflow). Prefer font_size 56-66 for base groups.\n"
        "6) Use grouped captions adaptively (1-5 words) with timings aligned to transcript windows.\n"
        "7) Split groups on long pause, sentence boundary (.!?), and when next word starts uppercase.\n"
        "8) Group timing must be exact: start=first word start, end=next group first-word start (last uses last word end).\n"
        "9) Use only supported animation refs.\n"
        "10) Use only supported semantic SFX/GIF/sticker keys.\n"
        "11) Keep timings within project duration and non-negative.\n"
        "12) In output inter.json, do NOT include transcript payloads or word_timing_map metadata; "
        "output grouped caption actions only.\n"
        "13) Use diverse palettes and backgrounds across scenes (including lighter morning-energy looks) while keeping caption contrast safe.\n"
        "14) Do NOT default to grid overlays. Use plain/tint/frame/panel backgrounds unless planner explicitly asks for map/calendar/grid look.\n"
        "15) Output must validate as one JSON object.\n\n"
        f"SUPPORTED_ANIMATION_REFS: {animations}\n"
        f"SUPPORTED_SEMANTIC_SFX_KEYS: {sfx_keys}\n"
        f"SUPPORTED_SEMANTIC_GIF_KEYS: {gif_keys}\n"
        f"SUPPORTED_SEMANTIC_STICKER_KEYS: {sticker_keys}\n\n"
        f"SUPPORTED_DESIGN_CATALOG:\n{design_catalog}\n\n"
        f"TARGET_INTER_SCHEMA_EXAMPLE:\n{schema_json}\n\n"
        f"USER_INSTRUCTION:\n{user_instruction}\n\n"
        f"PLANNER_TEXT:\n{planner_text}\n\n"
        f"ELEMENT_COMPACT:\n{element_compact_text}\n"
    )
