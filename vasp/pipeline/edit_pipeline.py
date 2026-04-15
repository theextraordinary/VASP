from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from vasp.a2v.caption_grouping import caption_grouping
from vasp.a2v.prompt_generator import a2v_prompt_generator
from vasp.llm.client import LLMClient
from vasp.core.json_compactor import compact_unified_element_json
from vasp.core.serialization import merge_serialized_bundle, serialize_element_json
from vasp.media_reader.pipeline import generate_input_json
from vasp.planner.service import plan_edit
from vasp.refiner.service import refine_plan
from vasp.render.element_renderer import render_from_json


def run_edit_pipeline(
    *,
    instruction: str,
    media_paths: list[Any],
    output_path: str,
    video_length_s: float | None = None,
    stop_after_serializer: bool = False,
    planner_model: str = "e2b",
    refiner_model: str = "e2b",
    extra_options: Optional[dict[str, Any]] = None,
    llm_client: Optional[LLMClient] = None,
    render: bool = True,
) -> Path:
    """Run the full multi-stage pipeline from media reader to renderer."""
    print("[PIPELINE] Starting run_edit_pipeline")
    llm_client = llm_client or LLMClient()
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    options = dict(extra_options or {})
    if video_length_s is not None:
        options["target_duration_s"] = float(video_length_s)

    media_json = generate_input_json(
        instruction=instruction,
        media_paths=media_paths,
        output_path=output_path,
        options=options,
    )
    media_path = out_dir / "media.json"
    media_path.write_text(json.dumps(media_json, indent=2), encoding="utf-8")
    print(f"[PIPELINE] Media Reader complete -> {media_path}")

    elements_json, element_props_json = serialize_element_json(media_json)
    unified_element_json = merge_serialized_bundle(elements_json, element_props_json, drop_nulls=True)
    unified_element_json = caption_grouping(
        unified_element_json,
        words_per_group=int(options.get("caption_group_words", 3)),
        pause_hold_threshold_s=float(options.get("caption_group_hold_gap_s", 0.18)),
    )
    element_path = out_dir / "element.json"
    element_path.write_text(json.dumps(unified_element_json, indent=2), encoding="utf-8")
    compact_element_path = compact_unified_element_json(
        element_json=unified_element_json,
        output_dir=out_dir,
    )
    print(f"[PIPELINE] Serializer complete -> {element_path}")
    print(f"[PIPELINE] Compact serializer snapshot -> {compact_element_path}")

    if stop_after_serializer:
        print("[PIPELINE] stop_after_serializer=True -> returning serializer artifact")
        return element_path

    a2v_prompt = a2v_prompt_generator(
        instruction=instruction,
        instruction_1=str(options.get("instruction_1", "")).strip() or None,
        instruction_2=str(options.get("instruction_2", "")).strip() or None,
        instruction_3=str(options.get("instruction_3", "")).strip() or None,
        media_json=media_json,
        element_json=unified_element_json,
    )
    a2v_prompt_path = out_dir / "a2v_prompt.txt"
    a2v_prompt_path.write_text(a2v_prompt, encoding="utf-8")
    print(f"[PIPELINE] A2V prompt prepared -> {a2v_prompt_path}")

    llm1_json = plan_edit(
        instruction=instruction,
        elements_json=unified_element_json,
        planner_prompt_override=a2v_prompt,
        model=planner_model,  # type: ignore[arg-type]
        client=llm_client,
    )
    llm1_path = out_dir / "llm1.json"
    llm1_path.write_text(json.dumps(llm1_json, indent=2), encoding="utf-8")
    print(f"[PIPELINE] Planner complete -> {llm1_path}")

    inter_json = refine_plan(
        instruction=instruction,
        llm1_json=llm1_json,
        element_json=unified_element_json,
        video_block=media_json["video"],
        model=refiner_model,  # type: ignore[arg-type]
        client=llm_client,
    )
    inter_json["properties_path"] = None
    inter_path = out_dir / "inter.json"
    inter_path.write_text(json.dumps(inter_json, indent=2), encoding="utf-8")
    print(f"[PIPELINE] Refiner complete -> {inter_path}")

    if render:
        print("[PIPELINE] Renderer starting...")
        return render_from_json(str(inter_path), strict=True)
    print("[PIPELINE] Render disabled; returning inter.json")
    return inter_path
