from __future__ import annotations

import json
from typing import Any, Optional

from vasp.animation.presets import expand_animation_actions
from vasp.design.preset_map import caption_design_params, visual_design_params
from vasp.llm.client import LLMClient
from vasp.llm.schemas import LLMRequest, LLMModel
from vasp.refiner.schemas import InterRenderPlan


def refine_plan(
    *,
    instruction: str,
    llm1_json: dict[str, Any],
    element_json: dict[str, Any],
    video_block: dict[str, Any],
    model: LLMModel = "e2b",
    client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """Refiner layer producing renderer-ready plan."""
    client = client or LLMClient()
    prompt = _build_refiner_prompt(instruction, llm1_json, element_json, video_block)
    req = LLMRequest(model=model, prompt=prompt, temperature=0.2)
    try:
        raw = client.generate_json(req)
        validated = InterRenderPlan.model_validate(raw)
    except Exception:
        validated = InterRenderPlan.model_validate(
            _build_refiner_fallback(
                instruction=instruction,
                llm1_json=llm1_json,
                element_json=element_json,
                video_block=video_block,
            )
        )

    # Post-process to ensure visible changes and centered defaults.
    enhanced = _enhance_refiner_output(
        instruction=instruction,
        llm1_json=llm1_json,
        element_json=element_json,
        inter=validated.model_dump(),
        video_block=video_block,
    )
    validated = InterRenderPlan.model_validate(enhanced)
    return json.loads(validated.model_dump_json())


def _build_refiner_prompt(
    instruction: str,
    llm1_json: dict[str, Any],
    element_json: dict[str, Any],
    video_block: dict[str, Any],
) -> str:
    compact_props = _compact_props(element_json)
    return (
        "You are Refiner (LLM-2). Output ONLY valid JSON that matches this schema:\n"
        "{\n"
        '  "version": "1.0",\n'
        '  "video": { ... },\n'
        '  "properties_path": null,\n'
        '  "elements": [\n'
        "    {\n"
        '      "element_id": "string",\n'
        '      "timing": {"start": 0.0, "duration": 1.0},\n'
        '      "actions": [\n'
        "        {\n"
        '          "t_start": 0.0,\n'
        '          "t_end": 1.0,\n'
        '          "op": "show",\n'
        '          "params": {"scale": 1.0}\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Use only fields that exist in element.json properties. Do not invent fields.\n"
        f"USER INSTRUCTION:\n{instruction}\n\n"
        f"VIDEO BLOCK:\n{json.dumps(video_block, indent=2)}\n\n"
        f"PLANNER OUTPUT (llm1.json):\n{json.dumps(llm1_json, indent=2)}\n\n"
        f"ELEMENT PROPS (compact):\n{json.dumps(compact_props, indent=2)}\n"
    )


def _build_refiner_fallback(
    *,
    instruction: str,
    llm1_json: dict[str, Any],
    element_json: dict[str, Any],
    video_block: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic fallback when model output is malformed/unusable."""
    _ = instruction
    source_map = {
        entry.get("element_id"): entry
        for entry in element_json.get("elements", [])
        if isinstance(entry, dict) and isinstance(entry.get("element_id"), str)
    }
    elements = []
    decisions = llm1_json.get("decisions", [])
    for d in decisions:
        element_id = d["element_id"]
        source_entry = source_map.get(element_id, {})
        elements.append(
            {
                "element_id": element_id,
                "type": source_entry.get("type"),
                "about": source_entry.get("about"),
                "aim": source_entry.get("aim"),
                "timing": {"start": d["t_start"], "duration": max(0.0, d["t_end"] - d["t_start"])},
                "properties": source_entry.get("properties", {}),
                "actions": [{"t_start": d["t_start"], "t_end": d["t_end"], "op": "show", "params": {}}],
            }
        )
    return {
        "version": "1.0",
        "video": video_block,
        "properties_path": None,
        "elements": elements,
    }


def _enhance_refiner_output(
    *,
    instruction: str,
    llm1_json: dict[str, Any],
    element_json: dict[str, Any],
    inter: dict[str, Any],
    video_block: dict[str, Any],
) -> dict[str, Any]:
    w = int(video_block.get("size", {}).get("width", 1080))
    h = int(video_block.get("size", {}).get("height", 1920))
    dramatic = "dramatic" in instruction.lower() or "bold" in instruction.lower()

    props_entries = element_json.get("elements", [])
    source_entry_map: dict[str, dict[str, Any]] = {
        e.get("element_id"): e
        for e in props_entries
        if isinstance(e, dict) and isinstance(e.get("element_id"), str)
    }
    prop_map: dict[str, dict[str, Any]] = {
        e.get("element_id"): dict(e.get("properties", {}))
        for e in props_entries
        if isinstance(e, dict) and isinstance(e.get("element_id"), str)
    }
    decisions = {d["element_id"]: d for d in llm1_json.get("decisions", [])}

    out_elements = []
    visual_index = 0
    for entry in inter.get("elements", []):
        element_id = entry.get("element_id")
        if not element_id:
            continue
        prop = prop_map.get(element_id, {})
        if not isinstance(prop, dict) or not prop.get("type"):
            # Ignore unknown planner/refiner ids that are not present in elementProps.
            continue
        d = decisions.get(element_id, {})
        t_start = float(d.get("t_start", entry.get("timing", {}).get("start", 0.0)))
        t_end = float(d.get("t_end", t_start + entry.get("timing", {}).get("duration", 0.0)))
        if t_end < t_start:
            t_end = t_start

        element_type = prop.get("type", "")
        op = "play" if element_type in ("music", "sfx") else "show"
        base_params: dict[str, Any] = {}

        # Apply design presets to visible media/caption params.
        design_ref = d.get("design_ref")
        if element_type == "caption":
            base_params.update(caption_design_params(design_ref, dramatic=dramatic))
        else:
            base_params.update(visual_design_params(design_ref, dramatic=dramatic))

        # Apply animation refs to action slicing.
        animation_ref = d.get("animation_ref") or ("subtle_zoom" if dramatic and element_type in ("video", "image", "gif") else None)
        source_length = _safe_float(prop.get("length"))

        if element_type in ("video", "image", "gif"):
            actions = _build_visual_motion_actions(
                t_start=t_start,
                t_end=t_end,
                base_params=base_params,
                visual_index=visual_index,
                w=w,
                h=h,
                source_length=source_length if element_type in ("video", "gif") else None,
                animation_ref=animation_ref,
            )
            visual_index += 1
        elif element_type in ("music", "sfx") and source_length and source_length > 0 and (t_end - t_start) > source_length:
            actions = _looped_actions(
                op=op,
                t_start=t_start,
                t_end=t_end,
                source_length=source_length,
                animation_ref=None,
                base_params=base_params,
            )
        else:
            actions = expand_animation_actions(
                animation_ref,
                op=op,
                t_start=t_start,
                t_end=t_end,
                base_params=base_params,
            )

        out_elements.append(
            {
                "element_id": element_id,
                "type": source_entry_map.get(element_id, {}).get("type"),
                "about": source_entry_map.get(element_id, {}).get("about"),
                "aim": source_entry_map.get(element_id, {}).get("aim"),
                "timing": {"start": t_start, "duration": max(0.0, t_end - t_start)},
                "properties": prop,
                "actions": actions,
            }
        )

        # Apply placement defaults directly into properties used by renderer.
        transform = dict(prop.get("transform", {}))
        zone = (d.get("placement_zone") or "center").lower()
        if zone == "bottom":
            transform["x"] = w / 2
            transform["y"] = h * 0.82
        elif zone == "top":
            transform["x"] = w / 2
            transform["y"] = h * 0.18
        elif zone == "left":
            transform["x"] = w * 0.25
            transform["y"] = h / 2
        elif zone == "right":
            transform["x"] = w * 0.75
            transform["y"] = h / 2
        else:
            transform["x"] = w / 2
            transform["y"] = h / 2
        prop["transform"] = transform
        if element_type == "caption":
            caption_text = d.get("caption_text")
            if caption_text:
                prop["text"] = caption_text
        prop_map[element_id] = prop

    if not out_elements:
        # Deterministic fallback from planner only
        for d in llm1_json.get("decisions", []):
            element_id = d["element_id"]
            prop = prop_map.get(element_id, {})
            if not isinstance(prop, dict) or not prop.get("type"):
                continue
            out_elements.append(
                {
                    "element_id": element_id,
                    "type": source_entry_map.get(element_id, {}).get("type"),
                    "about": source_entry_map.get(element_id, {}).get("about"),
                    "aim": source_entry_map.get(element_id, {}).get("aim"),
                    "timing": {"start": d["t_start"], "duration": max(0.0, d["t_end"] - d["t_start"])},
                    "properties": prop,
                    "actions": [{"t_start": d["t_start"], "t_end": d["t_end"], "op": "show", "params": {}}],
                }
            )

    inter["version"] = "1.0"
    inter["video"] = video_block
    inter["elements"] = out_elements
    inter.pop("updated_element_props", None)
    return inter


def _compact_props(element_json: dict[str, Any]) -> dict[str, Any]:
    compact = {"version": element_json.get("version"), "elements": []}
    for entry in element_json.get("elements", []):
        props = entry.get("properties", {})
        transform = props.get("transform", {})
        compact["elements"].append(
            {
                "element_id": entry.get("element_id"),
                "type": props.get("type"),
                "source_uri": props.get("source_uri"),
                "timing": props.get("timing"),
                "transform": {"x": transform.get("x"), "y": transform.get("y")},
            }
        )
    return compact




def _looped_actions(
    *,
    op: str,
    t_start: float,
    t_end: float,
    source_length: float,
    animation_ref: str | None,
    base_params: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    cursor = t_start
    segment_idx = 0
    while cursor < t_end:
        seg_end = min(t_end, cursor + source_length)
        params = dict(base_params)
        params["trim_in"] = 0.0
        params["trim_out"] = max(0.01, seg_end - cursor)
        # Progressive tiny scale drift creates visible movement across loops.
        params.setdefault("scale", 1.0 + min(0.12, segment_idx * 0.02))
        actions.extend(
            expand_animation_actions(
                animation_ref,
                op=op,
                t_start=cursor,
                t_end=seg_end,
                base_params=params,
            )
        )
        cursor = seg_end
        segment_idx += 1
    return actions


def _build_visual_motion_actions(
    *,
    t_start: float,
    t_end: float,
    base_params: dict[str, Any],
    visual_index: int,
    w: int,
    h: int,
    source_length: float | None,
    animation_ref: str | None,
) -> list[dict[str, Any]]:
    duration = max(0.0, t_end - t_start)
    if duration <= 0:
        return [{"t_start": t_start, "t_end": t_end, "op": "show", "params": dict(base_params)}]

    # Keep action count bounded to prevent oversized ffmpeg graphs.
    max_segments = 10
    segments = min(max_segments, max(3, int(duration / 4.0)))
    step = duration / segments
    times = [round(t_start + i * step, 6) for i in range(segments)]
    times.append(round(t_end, 6))

    anchors = [
        (0.50, 0.50),
        (0.34, 0.42),
        (0.66, 0.58),
        (0.42, 0.70),
        (0.58, 0.32),
        (0.26, 0.56),
        (0.74, 0.44),
    ]
    start_offset = visual_index % len(anchors)
    actions: list[dict[str, Any]] = []

    for i in range(len(times) - 1):
        seg_start = times[i]
        seg_end = times[i + 1]
        ax, ay = anchors[(start_offset + i) % len(anchors)]
        params = dict(base_params)
        params["x"] = float(w * ax)
        params["y"] = float(h * ay)
        params["scale"] = 0.92 + ((i + visual_index) % 4) * 0.06
        if i % 3 == 2:
            params["round_corners"] = 18

        if source_length and source_length > 0:
            # Keep short source media looping by timeline segment.
            local_offset = max(0.0, seg_start - t_start)
            trim_in = local_offset % source_length
            seg_dur = max(0.01, seg_end - seg_start)
            params["trim_in"] = trim_in
            params["trim_out"] = min(source_length, trim_in + seg_dur)
            if params["trim_out"] <= params["trim_in"]:
                params["trim_in"] = 0.0
                params["trim_out"] = min(source_length, seg_dur)

        # Use one action per segment; avoid doubling via expansion on long timelines.
        _ = animation_ref
        actions.append({"t_start": seg_start, "t_end": seg_end, "op": "show", "params": params})
    return actions


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
