import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running this file directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vasp.llm.client import LLMClient  # noqa: E402
from vasp.refiner.service import refine_plan  # noqa: E402
from vasp.render.element_renderer import render_from_json  # noqa: E402


def run_from_llm1(*, output_dir: Path, model: str, skip_render: bool = False) -> Path:
    media_path = output_dir / "media.json"
    llm1_path = output_dir / "llm1.json"
    props_path = output_dir / "elementProps.json"
    inter_path = output_dir / "inter.json"

    media = json.loads(media_path.read_text(encoding="utf-8"))
    llm1 = json.loads(llm1_path.read_text(encoding="utf-8"))
    props = json.loads(props_path.read_text(encoding="utf-8"))

    print(f"[MANUAL FLOW] Loaded media: {media_path}")
    print(f"[MANUAL FLOW] Loaded llm1: {llm1_path}")
    print(f"[MANUAL FLOW] Loaded props: {props_path}")

    inter = refine_plan(
        instruction=media["intent"]["instruction"],
        llm1_json=llm1,
        element_props_json=props,
        video_block=media["video"],
        model=model,  # type: ignore[arg-type]
        client=LLMClient(),
    )

    if isinstance(inter.get("updated_element_props"), list) and inter["updated_element_props"]:
        props["elements"] = inter["updated_element_props"]
        props_path.write_text(json.dumps(props, indent=2), encoding="utf-8")
        print(f"[MANUAL FLOW] Updated props -> {props_path}")

    inter["properties_path"] = str(props_path)
    inter_path.write_text(json.dumps(inter, indent=2), encoding="utf-8")
    print(f"[MANUAL FLOW] Refiner complete -> {inter_path}")

    if skip_render:
        print("[MANUAL FLOW] Render skipped (--skip-render).")
        return inter_path

    result = render_from_json(str(inter_path), strict=True)
    print("[MANUAL FLOW] Render complete ->", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run refiner+renderer using existing output/llm1.json.")
    parser.add_argument("--output-dir", default="output", help="Directory containing media.json, llm1.json, elementProps.json")
    parser.add_argument("--model", default="e2b", help="Refiner model key (e2b/e4b)")
    parser.add_argument("--skip-render", action="store_true", help="Only regenerate inter.json")
    args = parser.parse_args()

    run_from_llm1(output_dir=Path(args.output_dir), model=args.model, skip_render=args.skip_render)
