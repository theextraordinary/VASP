from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vasp.a2v.main import (
    PLANNER_PROMPT_TEMPLATE,
    _generate_planner_text_strict,
    _generate_refiner_json_strict,
    _ground_inter_with_element2,
    _strip_refiner_output_heavy_fields,
)
from vasp.core.json_compactor import compact_unified_element_json
from vasp.core.serialization import serialize_element2_json
from vasp.llm.client import LLMClient
from vasp.llm.schemas import LLMRequest
from vasp.media_reader.from_captions import create_media_json_from_captions_file
from vasp.refiner.prompt_templates import build_inter_refiner_prompt
from vasp.render.element_renderer import render_from_json


def run_captions_to_video_pipeline(
    *,
    captions_file: str | Path,
    instruction: str,
    output_video: str | Path = "output/a2v_video.mp4",
    planner_model: str = "e2b",
    refiner_model: str = "e2b",
    planner_endpoint: str | None = None,
    refiner_endpoint: str | None = None,
) -> dict[str, str]:
    """Single-command pipeline: captions.txt + media folder -> final rendered mp4."""
    out_dir = Path(output_video).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) media reader (captures ASR/transcript, probe, analysis)
    media_json = create_media_json_from_captions_file(
        captions_file_path=captions_file,
        output_media_json_path=out_dir / "media.json",
        instruction=instruction,
    )
    media_path = out_dir / "media.json"
    media_path.write_text(json.dumps(media_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) serializer v2 + compacter
    element2 = serialize_element2_json(media_json, drop_nulls=False)
    element2_path = out_dir / "element2.json"
    element2_path.write_text(json.dumps(element2, ensure_ascii=False, indent=2), encoding="utf-8")
    compact_path = compact_unified_element_json(
        element_json=element2,
        output_dir=out_dir,
        output_filename="element2_compact.txt",
    )

    # 3) planner
    planner_prompt = PLANNER_PROMPT_TEMPLATE.format(
        USER_INSTRUCTION=instruction,
        ELEMENTS=Path(compact_path).read_text(encoding="utf-8"),
    )
    (out_dir / "planner_prompt.txt").write_text(planner_prompt, encoding="utf-8")
    planner_client = _build_client(model=planner_model, endpoint=planner_endpoint)
    planner_req = LLMRequest(model=planner_model, prompt=planner_prompt, temperature=0.2)
    planner_resp = _generate_planner_text_strict(planner_client, planner_req, user_prompt=planner_prompt)
    planner_text = planner_resp.text.strip()
    planner_path = out_dir / "planner.txt"
    planner_path.write_text(planner_text + "\n", encoding="utf-8")

    # 4) refiner prompt + inter generation
    refiner_prompt = build_inter_refiner_prompt(
        user_instruction=instruction,
        planner_text=planner_text,
        element_compact_text=Path(compact_path).read_text(encoding="utf-8"),
    )
    refiner_prompt_path = out_dir / "refiner_prompt.txt"
    refiner_prompt_path.write_text(refiner_prompt, encoding="utf-8")
    refiner_client = _build_client(model=refiner_model, endpoint=refiner_endpoint)
    refiner_req = LLMRequest(model=refiner_model, prompt=refiner_prompt, temperature=0.1)
    inter_json = _generate_refiner_json_strict(refiner_client, refiner_req, planner_text=planner_text)
    inter_json = _ground_inter_with_element2(inter_json, element2)
    inter_json = _strip_refiner_output_heavy_fields(inter_json)
    inter_path = out_dir / "inter.json"
    inter_path.write_text(json.dumps(inter_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) render
    render_from_json(str(inter_path), strict=True)

    return {
        "media_json": str(media_path),
        "element2_json": str(element2_path),
        "element2_compact": str(compact_path),
        "planner_prompt": str(out_dir / "planner_prompt.txt"),
        "planner_txt": str(planner_path),
        "refiner_prompt": str(refiner_prompt_path),
        "inter_json": str(inter_path),
        "video": str(Path(output_video)),
    }


def _build_client(*, model: str, endpoint: str | None) -> LLMClient:
    if not endpoint:
        return LLMClient()
    if model == "e4b":
        return LLMClient(e4b_url=endpoint)
    return LLMClient(e2b_url=endpoint)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full A2V pipeline from captions.txt + media in same folder to final mp4."
    )
    parser.add_argument("--captions-file", required=True, help="Path to captions.txt/csv in media folder.")
    parser.add_argument("--instruction", required=True, help="High-level user instruction for the edit.")
    parser.add_argument("--output", default="output/a2v_video.mp4", help="Final rendered video path.")
    parser.add_argument("--planner-model", default="e2b", choices=("e2b", "e4b"))
    parser.add_argument("--refiner-model", default="e2b", choices=("e2b", "e4b"))
    parser.add_argument("--planner-endpoint", default=None, help="Optional planner endpoint override.")
    parser.add_argument("--refiner-endpoint", default=None, help="Optional refiner endpoint override.")
    args = parser.parse_args()

    result = run_captions_to_video_pipeline(
        captions_file=args.captions_file,
        instruction=args.instruction,
        output_video=args.output,
        planner_model=args.planner_model,
        refiner_model=args.refiner_model,
        planner_endpoint=args.planner_endpoint,
        refiner_endpoint=args.refiner_endpoint,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

