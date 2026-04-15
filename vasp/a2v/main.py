from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from vasp.core.json_compactor import compact_unified_element_json
from vasp.core.serialization import serialize_element2_json
from vasp.llm.client import LLMClient
from vasp.llm.schemas import LLMRequest
from vasp.media_reader.pipeline import generate_input_json
from vasp.pipeline.edit_pipeline import run_edit_pipeline
from vasp.render.element_renderer import render_from_json
from vasp.refiner.prompt_templates import build_inter_refiner_prompt

EXAMPLE_COMMAND = (
    "python -m vasp.a2v.main "
    '--instruction "Create a caption-first A2V reel" '
    '--media-tuple "assets/inputs/video.mp4" "extract speech captions" "talking-head clip about AI tools" '
    '--media-tuple "assets/inputs/music.mp3" "background bed" "energetic music track" '
    "--output output/a2v_video.mp4 "
    "--video-length 30 "
    '--instruction-1 "Highlight key spoken words" '
    '--instruction-2 "Keep caption pacing tight" '
    '--instruction-3 "Use clean modern style"'
)

DUMMY_INPUT = {
    "instruction": "Create a caption-aware A2V reel with strong pacing from speech and background music.",
    "media": [
        ("assets/inputs/audio.wav", "extract speech captions", "audio about history"),
        ("assets/inputs/image.jpg", "use scratch animation for its entrance", "its Johaness Kepler in the image"),
    ],
    "output": "output/a2v_video.mp4",
    "video_length": 30.0,
    "instruction_1": "Highlight important spoken words.",
    "instruction_2": "Use pauses to drive emphasis.",
    "instruction_3": "Keep captions clean and readable.",
}

PLANNER_PROMPT_TEMPLATE = (
    "Task: Generate a structured language edit plan for a short-form video. "
    "User Instruction: {USER_INSTRUCTION} "
    "Goal: Create a smooth, engaging, high-retention edit using the provided elements. "
    "Priority Order: [Audio, Caption, Image, Video, Sfx, Gif] "
    "Rules: - Start from an empty video canvas. "
    "- Use the main audio as the full timeline backbone. "
    "- Divide the video into meaningful segments using caption timing, topic changes, silence, emphasis, and pacing. "
    "- Segments may be caption-focused, visual-focused, transition-focused, or mixed. "
    "- Keep captions readable at all times. "
    "- Never let visuals cover important captions. "
    "- Keep one consistent style across the full video unless a strong moment needs extra emphasis. "
    "- Highlight the currently spoken caption word. "
    "- Correct a caption word only if it is clearly wrong and the intended word is obvious from context. "
    "- Use images, videos, gifs, SFX, and music only when they match the spoken topic or improve the edit. "
    "- Prefer showing media exactly when the related topic, object, person, or event is mentioned. "
    "- Each element may contain: - about = what the element contains or represents - aim = preferred use of the element "
    "- Prefer aim over about if both exist. Either may be empty. "
    "- If aim exists, try to satisfy it unless it strongly harms the edit. "
    "- If there is no good media match, keep the segment caption-focused. "
    "- Use position, crop, scale, transitions, zoom, motion, glow, entrance, exit, split layout, background color, gradient, blur, or design treatment only when they improve clarity, engagement, or flow. "
    "- Use SFX only on important words, transitions, punchlines, or impact moments. "
    "- Keep background music below speech when both are present. "
    "- Caption grouping must be adaptive: 1-5 words per group (never more than 5). "
    "- Split caption groups on long pause, sentence boundary (.!?), and when next word starts with uppercase. "
    "- Group timing must be exact: group start = first word start, group end = next group first-word start (last group ends at last word end). "
    "- Important-word highlighting must affect only the specific word(s), not the whole sentence color. "
    "- Keep all captions fully inside 9:16 safe area. "
    "- Use diverse color palettes across scenes (including lighter energetic morning palettes) while preserving contrast/readability. "
    "- Do not overuse grids; default to plain color, gradient, tint, panel, or frame unless calendar/map/grid is explicitly needed. "
    "- Use different background styles/design layers across segments when it improves engagement and still keeps captions clear. "
    "- Maximize engagement, readability, relevance, smoothness, and retention. "
    "You should be able to decide the time duration where multiple caption should be placed on the screen at once, along with which word is important and what to color and highlight "
    "Elements:\n{ELEMENTS}\n"
    "Output: Return ONLY the following structure: "
    "EDIT PLAN "
    "Global Style: "
    "Audio Decision: "
    "Caption Style: "
    "Visual Style: "
    "Background Style: "
    "Segmentation Rule: "
    "Segment 1 "
    "Time: "
    "Purpose: "
    "Elements Used: "
    "Caption Decision: "
    "Visual Decision: "
    "Animation Decision: "
    "Placement Decision: "
    "Timing Events: - time: event "
    "Transition Out: "
    "Engagement Note: "
    "Segment 2 ... Repeat for all segments. "
    "Constraints: - Do NOT return JSON. - Do NOT return code. - Do NOT explain reasoning. "
    "- Use exact element ids and times whenever possible. "
    "- Keep the exact same headings every time. "
    "- Make the result easy to convert into JSON later."
)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="A2V runner: user instruction + media paths -> VASP pipeline outputs/video."
    )
    parser.add_argument("--instruction", required=False, help="Primary user instruction.")
    parser.add_argument(
        "--media",
        required=False,
        nargs="+",
        help="One or more media paths (video/image/gif/audio).",
    )
    parser.add_argument(
        "--media-tuple",
        required=False,
        nargs=3,
        action="append",
        metavar=("PATH", "AIM", "ABOUT"),
        help="Media tuple input. Repeat for multiple items. AIM/ABOUT can be empty strings.",
    )
    parser.add_argument(
        "--output",
        default="output/a2v_video.mp4",
        help="Final output video path for full pipeline mode.",
    )
    parser.add_argument(
        "--mode",
        choices=("a2v", "full", "serializer", "serializer_v2", "planner_text", "planner_to_video", "build_refiner_prompt"),
        default="a2v",
        help=(
            "`a2v`: complete A2V flow -> media.json, element2.json, element2_compact.txt, planner.txt, refiner_prompt.txt, inter.json, a2v_video.mp4. "
            "`full`: run end-to-end to mp4. "
            "`serializer`: stop after element.json. "
            "`serializer_v2`: create element2.json (single combined caption element + word time mapping). "
            "`planner_text`: call e2b/e4b endpoint with compact elements and save planner.txt. "
            "`planner_to_video`: convert planner.txt to inter.json via e2b/e4b and render final mp4. "
            "`build_refiner_prompt`: write robust refiner prompt from planner.txt + element_compact.txt."
        ),
    )
    parser.add_argument("--video-length", type=float, default=None, help="Target output duration in seconds.")
    parser.add_argument("--planner-model", default="e2b", choices=("e2b", "e4b"))
    parser.add_argument("--refiner-model", default="e2b", choices=("e2b", "e4b"))
    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--instruction-1", default=None)
    parser.add_argument("--instruction-2", default=None)
    parser.add_argument("--instruction-3", default=None)
    parser.add_argument("--asr-enabled", default="true", choices=("true", "false"))
    parser.add_argument("--asr-model-size", default="small")
    parser.add_argument(
        "--caption-group-words",
        type=int,
        default=3,
        help="Group N consecutive ASR words into one caption element (default: 3).",
    )
    parser.add_argument(
        "--caption-group-hold-gap",
        type=float,
        default=0.18,
        help="If gap between two caption groups is <= this seconds, keep previous group on-screen until next starts.",
    )
    parser.add_argument(
        "--use-dummy",
        action="store_true",
        help="Use built-in dummy inputs from DUMMY_INPUT in this file.",
    )
    parser.add_argument(
        "--compact-path",
        default="output/element2_compact.txt",
        help="Path to compact element text file used by planner_text mode.",
    )
    parser.add_argument(
        "--planner-output",
        default="output/planner.txt",
        help="Path to write planner text output in planner_text mode.",
    )
    parser.add_argument(
        "--planner-endpoint",
        default=None,
        help="Optional ngrok endpoint URL override for planner model (e2b/e4b).",
    )
    parser.add_argument(
        "--planner-input",
        default="output/planner.txt",
        help="Path to planner text file (from planner_text mode).",
    )
    parser.add_argument(
        "--element2-path",
        default="output/element2.json",
        help="Path to element2.json used as source for inter generation.",
    )
    parser.add_argument(
        "--inter-output",
        default="output/inter.json",
        help="Where to save generated inter.json in planner_to_video mode.",
    )
    parser.add_argument(
        "--refiner-prompt-output",
        default="output/refiner_prompt.txt",
        help="Path to write robust refiner prompt.",
    )
    args = parser.parse_args()
    args = _apply_dummy_defaults(args)

    options = _build_options(args)
    print(f"[A2V] Media inputs -> {_resolved_media(args)}")

    if args.mode == "serializer":
        element_path = run_edit_pipeline(
            instruction=args.instruction,
            media_paths=_resolved_media(args),
            output_path=args.output,
            video_length_s=args.video_length,
            planner_model=args.planner_model,
            refiner_model=args.refiner_model,
            extra_options=options,
            stop_after_serializer=True,
            render=False,
        )
        print(f"[A2V] Serializer-only pipeline complete -> {element_path}")
        return

    if args.mode == "a2v":
        # 1) media.json + element2.json + element2_compact.txt
        out_dir = Path(args.output).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        options = dict(options)
        if args.video_length is not None:
            options["target_duration_s"] = float(args.video_length)
        media_json = generate_input_json(
            instruction=args.instruction,
            media_paths=_resolved_media(args),
            output_path=args.output,
            options=options,
        )
        media_path = out_dir / "media.json"
        media_path.write_text(json.dumps(media_json, indent=2), encoding="utf-8")
        element2_json = serialize_element2_json(media_json, drop_nulls=True)
        element2_path = out_dir / "element2.json"
        element2_path.write_text(json.dumps(element2_json, indent=2), encoding="utf-8")
        element2_compact_path = compact_unified_element_json(
            element_json=element2_json,
            output_dir=out_dir,
            output_filename="element2_compact.txt",
        )
        print(f"[A2V] Media Reader complete -> {media_path}")
        print(f"[A2V] Serializer v2 complete -> {element2_path}")
        print(f"[A2V] Serializer v2 compact -> {element2_compact_path}")

        # 2) planner.txt
        planner_path = _run_planner_text(args)
        print(f"[A2V] Planner text complete -> {planner_path}")

        # 3) refiner_prompt.txt -> inter.json -> a2v_video.mp4
        inter_path, final_path = _run_planner_to_video(args)
        print(f"[A2V] Inter generation complete -> {inter_path}")
        print(f"[A2V] Render complete -> {final_path}")
        return

    if args.mode == "serializer_v2":
        out_dir = Path(args.output).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        options = dict(options)
        if args.video_length is not None:
            options["target_duration_s"] = float(args.video_length)
        media_json = generate_input_json(
            instruction=args.instruction,
            media_paths=_resolved_media(args),
            output_path=args.output,
            options=options,
        )
        media_path = out_dir / "media.json"
        media_path.write_text(json.dumps(media_json, indent=2), encoding="utf-8")
        element2_json = serialize_element2_json(media_json, drop_nulls=True)
        element2_path = out_dir / "element2.json"
        element2_path.write_text(json.dumps(element2_json, indent=2), encoding="utf-8")
        element2_compact_path = compact_unified_element_json(
            element_json=element2_json,
            output_dir=out_dir,
            output_filename="element2_compact.txt",
        )
        print(f"[A2V] Media Reader complete -> {media_path}")
        print(f"[A2V] Serializer v2 complete -> {element2_path}")
        print(f"[A2V] Serializer v2 compact -> {element2_compact_path}")
        return

    if args.mode == "planner_text":
        planner_path = _run_planner_text(args)
        print(f"[A2V] Planner text complete -> {planner_path}")
        return

    if args.mode == "build_refiner_prompt":
        path = _run_build_refiner_prompt(args)
        print(f"[A2V] Refiner prompt complete -> {path}")
        return

    if args.mode == "planner_to_video":
        inter_path, final_path = _run_planner_to_video(args)
        print(f"[A2V] Inter generation complete -> {inter_path}")
        print(f"[A2V] Render complete -> {final_path}")
        return

    final_path = run_edit_pipeline(
        instruction=args.instruction,
        media_paths=_resolved_media(args),
        output_path=args.output,
        video_length_s=args.video_length,
        planner_model=args.planner_model,
        refiner_model=args.refiner_model,
        extra_options=options,
        render=True,
    )
    print(f"[A2V] Done -> {final_path}")
    print(f"[A2V] Example command:\n{EXAMPLE_COMMAND}")


def _build_options(args: argparse.Namespace) -> dict[str, Any]:
    options: dict[str, Any] = {
        "asr_enabled": args.asr_enabled.lower() == "true",
        "asr_model_size": args.asr_model_size,
        "caption_group_words": max(1, int(args.caption_group_words)),
        "caption_group_hold_gap_s": max(0.0, float(args.caption_group_hold_gap)),
    }
    if args.fps is not None:
        options["fps"] = args.fps
    if args.instruction_1:
        options["instruction_1"] = args.instruction_1
    if args.instruction_2:
        options["instruction_2"] = args.instruction_2
    if args.instruction_3:
        options["instruction_3"] = args.instruction_3
    return options


def _apply_dummy_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Apply dummy defaults only when explicitly requested."""
    if args.instruction and (args.media or args.media_tuple):
        return args

    if args.use_dummy:
        args.instruction = DUMMY_INPUT["instruction"]
        args.media_tuple = [list(item) for item in DUMMY_INPUT["media"]]
        args.media = None
        args.output = args.output or str(DUMMY_INPUT["output"])
        if args.video_length is None:
            args.video_length = float(DUMMY_INPUT["video_length"])
        args.instruction_1 = args.instruction_1 or str(DUMMY_INPUT["instruction_1"])
        args.instruction_2 = args.instruction_2 or str(DUMMY_INPUT["instruction_2"])
        args.instruction_3 = args.instruction_3 or str(DUMMY_INPUT["instruction_3"])
        print("[A2V] Running with built-in dummy inputs (--use-dummy).")
        print(f"[A2V] Example command:\n{EXAMPLE_COMMAND}")
        return args

    raise SystemExit(
        "Missing required inputs: provide --instruction and --media ...\n"
        f"Example:\n{EXAMPLE_COMMAND}\n"
        "Or run with --use-dummy"
    )


def _resolved_media(args: argparse.Namespace) -> list[Any]:
    if args.media_tuple:
        # Convert [PATH, AIM, ABOUT] lists into tuple input contract.
        return [tuple(item) for item in args.media_tuple]
    return args.media or []


def _run_planner_text(args: argparse.Namespace) -> Path:
    compact_path = Path(args.compact_path)
    if not compact_path.exists():
        raise SystemExit(
            f"Missing compact file: {compact_path}\n"
            "Run serializer_v2 first, e.g.:\n"
            "python -m vasp.a2v.main --mode serializer_v2 --use-dummy"
        )

    elements_text = compact_path.read_text(encoding="utf-8")
    prompt = PLANNER_PROMPT_TEMPLATE.format(
        USER_INSTRUCTION=args.instruction,
        ELEMENTS=elements_text,
    )

    client_kwargs: dict[str, str] = {}
    if args.planner_endpoint:
        if args.planner_model == "e2b":
            client_kwargs["e2b_url"] = args.planner_endpoint
        else:
            client_kwargs["e4b_url"] = args.planner_endpoint
    client = LLMClient(**client_kwargs)

    req = LLMRequest(model=args.planner_model, prompt=prompt, temperature=0.2)
    print(f"[A2V] Planner calling model={args.planner_model} endpoint override={bool(args.planner_endpoint)}")
    response = client.generate_text(req)

    out_path = Path(args.planner_output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(response.text.strip() + "\n", encoding="utf-8")
    return out_path


def _run_planner_to_video(args: argparse.Namespace) -> tuple[Path, Path]:
    planner_path = Path(args.planner_input)
    element2_path = Path(args.element2_path)
    compact_path = Path(args.compact_path)

    if not planner_path.exists():
        raise SystemExit(f"Missing planner text file: {planner_path}")
    if not element2_path.exists():
        raise SystemExit(f"Missing element2 file: {element2_path}")
    if not compact_path.exists():
        raise SystemExit(f"Missing compact file: {compact_path}")

    planner_text = planner_path.read_text(encoding="utf-8")
    element2_json = json.loads(element2_path.read_text(encoding="utf-8"))
    compact_text = compact_path.read_text(encoding="utf-8")

    prompt = build_inter_refiner_prompt(
        user_instruction=args.instruction,
        planner_text=_trim_chars(planner_text, max_chars=18000),
        element_compact_text=_trim_chars(compact_text, max_chars=30000),
    )
    prompt_path = Path(args.refiner_prompt_output)
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"[A2V] Refiner prompt written -> {prompt_path}")

    client_kwargs: dict[str, str] = {}
    if args.planner_endpoint:
        if args.planner_model == "e2b":
            client_kwargs["e2b_url"] = args.planner_endpoint
        else:
            client_kwargs["e4b_url"] = args.planner_endpoint
    client = LLMClient(**client_kwargs)
    req = LLMRequest(model=args.planner_model, prompt=prompt, temperature=0.2)
    print(f"[A2V] Inter generation calling model={args.planner_model} endpoint override={bool(args.planner_endpoint)}")
    try:
        inter_json = client.generate_json(req)
    except Exception as exc:
        print(f"[A2V] Primary JSON parse failed, trying repair flow: {exc}")
        try:
            raw_text = client.generate_text(req).text
            inter_json = _try_parse_json_loose(raw_text)
        except Exception:
            try:
                repair_prompt = (
                    "Convert the following content into STRICT valid JSON only.\n"
                    "Do not add explanations. Keep the same schema and values where possible.\n\n"
                    f"{raw_text if 'raw_text' in locals() else ''}"
                )
                repair_req = LLMRequest(model=args.planner_model, prompt=repair_prompt, temperature=0.0)
                repaired_text = client.generate_text(repair_req).text
                inter_json = _try_parse_json_loose(repaired_text)
            except Exception as repair_exc:
                raise SystemExit(
                    "Inter generation failed from endpoint.\n"
                    f"Reason: {repair_exc}\n"
                    "Tips:\n"
                    f"1. Open {prompt_path} and reduce prompt size.\n"
                    "2. Check endpoint logs for context/tokenization errors.\n"
                    "3. Keep endpoint response to JSON only."
                ) from repair_exc

    inter_json = _ground_inter_with_element2(inter_json, element2_json)
    inter_json = _strip_refiner_output_heavy_fields(inter_json)

    inter_path = Path(args.inter_output)
    inter_path.parent.mkdir(parents=True, exist_ok=True)
    inter_path.write_text(json.dumps(inter_json, indent=2), encoding="utf-8")

    final_path = Path(args.output)
    render_from_json(str(inter_path), strict=True)
    return inter_path, final_path


def _run_build_refiner_prompt(args: argparse.Namespace) -> Path:
    planner_path = Path(args.planner_input)
    compact_path = Path(args.compact_path)
    if not planner_path.exists():
        raise SystemExit(f"Missing planner text file: {planner_path}")
    if not compact_path.exists():
        raise SystemExit(f"Missing compact file: {compact_path}")
    planner_text = planner_path.read_text(encoding="utf-8")
    compact_text = compact_path.read_text(encoding="utf-8")
    prompt = build_inter_refiner_prompt(
        user_instruction=args.instruction,
        planner_text=planner_text,
        element_compact_text=compact_text,
    )
    out = Path(args.refiner_prompt_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    return out

def _trim_chars(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[TRUNCATED]..."


def _ground_inter_with_element2(inter_json: dict[str, Any], element2_json: dict[str, Any]) -> dict[str, Any]:
    """Repair LLM inter output by grounding types/properties/paths/timings from element2 source."""
    grounded = deepcopy(inter_json) if isinstance(inter_json, dict) else {}
    source_elements = element2_json.get("elements", []) if isinstance(element2_json, dict) else []
    source_map: dict[str, dict[str, Any]] = {
        str(e.get("element_id")): e
        for e in source_elements
        if isinstance(e, dict) and isinstance(e.get("element_id"), str)
    }
    project_video = element2_json.get("video", {}) if isinstance(element2_json, dict) else {}
    grounded["version"] = str(grounded.get("version", "1.1"))
    grounded["video"] = project_video or grounded.get("video", {})
    grounded["properties_path"] = None

    # Compute project max end from source elements.
    project_end = 0.0
    for e in source_elements:
        if not isinstance(e, dict):
            continue
        timing = e.get("timing", {}) if isinstance(e.get("timing"), dict) else {}
        start = _to_float(timing.get("start"), 0.0)
        dur = max(0.0, _to_float(timing.get("duration"), 0.0))
        project_end = max(project_end, start + dur)
    if project_end <= 0.0:
        project_end = 60.0

    fixed_elements: list[dict[str, Any]] = []
    for raw in grounded.get("elements", []):
        if not isinstance(raw, dict):
            continue
        element_id = raw.get("element_id")
        if not isinstance(element_id, str):
            continue
        src = source_map.get(element_id)
        if not src:
            # Drop hallucinated elements that are not in element2.
            continue

        src_props = deepcopy(src.get("properties", {})) if isinstance(src.get("properties"), dict) else {}
        raw_props = raw.get("properties", {}) if isinstance(raw.get("properties"), dict) else {}

        # Merge but keep trusted source fields.
        merged_props = deepcopy(src_props)
        merged_props.update(raw_props)
        if src_props.get("source_uri"):
            merged_props["source_uri"] = src_props.get("source_uri")
        if src_props.get("type"):
            merged_props["type"] = src_props.get("type")
        if src_props.get("transform"):
            merged_props["transform"] = src_props.get("transform")
        if merged_props.get("source_uri") in ("...", "", None):
            merged_props.pop("source_uri", None)

        element_type = str(src.get("type") or merged_props.get("type") or raw.get("type") or "")
        if element_type == "audio":
            element_type = "music"
        if element_type == "caption":
            meta = merged_props.get("metadata")
            if isinstance(meta, dict):
                meta.pop("word_timing_map", None)
                meta.pop("transcript", None)
                if not meta:
                    merged_props.pop("metadata", None)

        # Timing: clamp to project window and source availability.
        src_timing = src.get("timing", {}) if isinstance(src.get("timing"), dict) else {}
        raw_timing = raw.get("timing", {}) if isinstance(raw.get("timing"), dict) else {}
        src_start = _to_float(src_timing.get("start"), 0.0)
        src_dur = max(0.0, _to_float(src_timing.get("duration"), project_end))
        src_end = src_start + src_dur

        raw_start = _to_float(raw_timing.get("start"), src_start)
        raw_dur = max(0.0, _to_float(raw_timing.get("duration"), src_dur))
        start = max(0.0, raw_start)
        end = min(project_end, start + raw_dur)
        if end <= start:
            start = src_start
            end = min(project_end, src_end if src_end > src_start else src_start + 1.0)

        raw_actions = raw.get("actions", []) if isinstance(raw.get("actions"), list) else []
        actions: list[dict[str, Any]] = []
        for a in raw_actions:
            if not isinstance(a, dict):
                continue
            t0 = max(start, _to_float(a.get("t_start"), start))
            t1 = min(end, _to_float(a.get("t_end"), end))
            if t1 <= t0:
                continue
            op_default = "play" if element_type in ("music", "sfx") else "show"
            op = str(a.get("op") or op_default)
            params = a.get("params", {}) if isinstance(a.get("params"), dict) else {}
            actions.append({"t_start": round(t0, 3), "t_end": round(t1, 3), "op": op, "params": params})

        if element_type == "caption":
            actions = _retime_caption_actions_from_word_map(actions, src_props)

        if not actions:
            op_default = "play" if element_type in ("music", "sfx") else "show"
            actions = [{"t_start": round(start, 3), "t_end": round(end, 3), "op": op_default, "params": {}}]

        if element_type == "caption" and actions:
            start = min(float(a.get("t_start", start)) for a in actions)
            end = max(float(a.get("t_end", end)) for a in actions)

        fixed_elements.append(
            {
                "element_id": element_id,
                "type": element_type,
                "about": raw.get("about", src.get("about")),
                "aim": raw.get("aim", src.get("aim")),
                "timing": {"start": round(start, 3), "duration": round(max(0.0, end - start), 3)},
                "properties": merged_props,
                "actions": actions,
            }
        )

    if not fixed_elements:
        # Hard fallback: source elements directly.
        for src in source_elements:
            if not isinstance(src, dict):
                continue
            element_id = src.get("element_id")
            if not isinstance(element_id, str):
                continue
            timing = src.get("timing", {}) if isinstance(src.get("timing"), dict) else {}
            start = _to_float(timing.get("start"), 0.0)
            dur = max(0.0, _to_float(timing.get("duration"), 1.0))
            element_type = str(src.get("type") or src.get("properties", {}).get("type") or "")
            if element_type == "audio":
                element_type = "music"
            op = "play" if element_type in ("music", "sfx") else "show"
            fixed_elements.append(
                {
                    "element_id": element_id,
                    "type": element_type,
                    "about": src.get("about"),
                    "aim": src.get("aim"),
                    "timing": {"start": round(start, 3), "duration": round(dur, 3)},
                    "properties": deepcopy(src.get("properties", {})),
                    "actions": [{"t_start": round(start, 3), "t_end": round(start + dur, 3), "op": op, "params": {}}],
                }
            )

    grounded["elements"] = fixed_elements
    return grounded


def _retime_caption_actions_from_word_map(actions: list[dict[str, Any]], src_props: dict[str, Any]) -> list[dict[str, Any]]:
    """Align caption group timings with caption word map from element2 serializer."""
    if not actions:
        return actions
    meta = src_props.get("metadata") if isinstance(src_props.get("metadata"), dict) else {}
    mapping = meta.get("word_timing_map") if isinstance(meta.get("word_timing_map"), list) else []
    words: list[dict[str, Any]] = [w for w in mapping if isinstance(w, dict)]
    if not words:
        return actions

    def _norm_token(token: str) -> str:
        token = token.strip().lower()
        return "".join(ch for ch in token if ch.isalnum() or ch == "'")

    def _regen_from_map(base_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Rebuild groups directly from current song map so stale captions cannot leak.
        style_params: dict[str, Any] = {}
        for a in base_actions:
            p = a.get("params") if isinstance(a.get("params"), dict) else {}
            if p:
                style_params = deepcopy(p)
                break
        # Keep style, but text/timings are regenerated from mapped words.
        style_params.pop("text", None)

        groups: list[list[dict[str, Any]]] = []
        cur: list[dict[str, Any]] = []
        for idx, w in enumerate(words):
            if not cur:
                cur = [w]
                continue
            prev = cur[-1]
            gap = _to_float(w.get("start"), 0.0) - _to_float(prev.get("end"), 0.0)
            prev_t = str(prev.get("text", ""))
            cur_t = str(w.get("text", ""))
            split = (
                gap > 0.18
                or prev_t.endswith((".", "!", "?"))
                or cur_t[:1].isupper()
                or len(cur) >= 5
            )
            if split:
                groups.append(cur)
                cur = [w]
            else:
                cur.append(w)
            # avoid creating too many tiny groups in very dense captions
            if idx == len(words) - 1 and cur:
                groups.append(cur)

        rebuilt: list[dict[str, Any]] = []
        for i, g in enumerate(groups):
            t_start = round(_to_float(g[0].get("start"), 0.0), 3)
            if i + 1 < len(groups):
                t_end = round(_to_float(groups[i + 1][0].get("start"), t_start + 0.03), 3)
            else:
                t_end = round(_to_float(g[-1].get("end"), t_start + 0.03), 3)
            if t_end <= t_start:
                t_end = round(t_start + 0.03, 3)
            params = deepcopy(style_params)
            params["text"] = " ".join(str(x.get("text", "")).strip() for x in g if str(x.get("text", "")).strip())
            rebuilt.append({"t_start": t_start, "t_end": t_end, "op": "show", "params": params})
        return rebuilt

    map_tokens = [_norm_token(str(w.get("text", ""))) for w in words]
    last_cursor = 0
    matched: list[tuple[int, int] | None] = []

    # Match each caption group's text to contiguous whisper words in-order.
    for action in actions:
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        text = str(params.get("text", "")).strip()
        tokens = [_norm_token(t) for t in text.split() if _norm_token(t)]
        if not tokens:
            matched.append(None)
            continue

        found: tuple[int, int] | None = None
        max_start = max(last_cursor, 0)
        for i in range(max_start, len(map_tokens) - len(tokens) + 1):
            if map_tokens[i : i + len(tokens)] == tokens:
                found = (i, i + len(tokens) - 1)
                break
        if found is None:
            # fallback: global search (still contiguous)
            for i in range(0, len(map_tokens) - len(tokens) + 1):
                if map_tokens[i : i + len(tokens)] == tokens:
                    found = (i, i + len(tokens) - 1)
                    break
        matched.append(found)
        if found is not None:
            s, e = found
            action["t_start"] = round(float(words[s].get("start", action.get("t_start", 0.0))), 3)
            last_cursor = e + 1

    # End times: next group's start (except last group, uses last matched word end).
    for i, found in enumerate(matched):
        if found is None:
            continue
        _s, e = found
        if i + 1 < len(actions):
            nxt = float(actions[i + 1].get("t_start", actions[i].get("t_end", 0.0)))
            cur = float(actions[i].get("t_start", 0.0))
            actions[i]["t_end"] = round(max(cur, nxt), 3)
        else:
            actions[i]["t_end"] = round(float(words[e].get("end", actions[i].get("t_end", 0.0))), 3)

    # If most groups did not match this map, captions likely came from a previous song.
    matched_count = sum(1 for m in matched if m is not None)
    if matched_count == 0 or matched_count < max(1, int(0.6 * len(actions))):
        return _regen_from_map(actions)

    # Ensure strictly valid intervals.
    for action in actions:
        t0 = float(action.get("t_start", 0.0))
        t1 = float(action.get("t_end", t0))
        if t1 <= t0:
            t1 = t0 + 0.03
        action["t_start"] = round(t0, 3)
        action["t_end"] = round(t1, 3)
    return actions


def _strip_refiner_output_heavy_fields(inter_json: dict[str, Any]) -> dict[str, Any]:
    """Keep refiner output lean: grouping/actions only, no duplicated timing maps."""
    if not isinstance(inter_json, dict):
        return inter_json
    for element in inter_json.get("elements", []):
        if not isinstance(element, dict):
            continue
        if str(element.get("type", "")).lower() != "caption":
            continue
        props = element.get("properties")
        if not isinstance(props, dict):
            continue
        meta = props.get("metadata")
        if not isinstance(meta, dict):
            continue
        meta.pop("word_timing_map", None)
        meta.pop("transcript", None)
        if not meta:
            props.pop("metadata", None)
    return inter_json


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _try_parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    block = _extract_first_json_object(text)
    parsed = json.loads(block)
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON must be an object")
    return parsed


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object start found")

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("No complete JSON object found")


if __name__ == "__main__":
    main()
