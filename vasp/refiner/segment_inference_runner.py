from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx


def run_refiner_for_segment_prompts(
    *,
    prompts_dir: str | Path,
    endpoint: str,
    output_dir: str | Path = "output/refiner_segment_outputs",
    temperature: float = 0.1,
    max_tokens: int = 2400,
    timeout_s: float = 420.0,
) -> dict[str, Any]:
    """Call refiner endpoint for each segment prompt, one-by-one, and save outputs."""
    pdir = Path(prompts_dir)
    if not pdir.exists() or not pdir.is_dir():
        raise FileNotFoundError(f"prompts_dir not found: {pdir}")
    if not endpoint.strip():
        raise ValueError("endpoint is required")

    prompt_files = sorted(
        [
            p
            for p in pdir.glob("refiner_segment_prompt_*.txt")
            if p.is_file()
        ]
    )
    if not prompt_files:
        raise FileNotFoundError(f"No segment prompts found in {pdir}")

    odir = Path(output_dir)
    odir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for i, prompt_file in enumerate(prompt_files, start=1):
        prompt = prompt_file.read_text(encoding="utf-8")
        status_code = 0
        raw_text = ""
        parsed_ok = False
        parse_error = None
        output_json_path = None
        validation_errors: list[str] = []
        max_attempts = 3
        last_obj: dict[str, Any] | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = httpx.post(
                    endpoint,
                    json={"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens},
                    timeout=timeout_s,
                )
            except Exception as exc:
                status_code = 0
                raw_text = str(exc)
                parse_error = f"http_error: {exc}"
                break

            status_code = int(response.status_code)
            if status_code >= 400:
                try:
                    raw_text = response.text
                except Exception:
                    raw_text = ""
                parse_error = f"http_status_{status_code}"
                break

            payload = response.json()
            raw_text = payload.get("response", "") if isinstance(payload, dict) else str(payload)
            try:
                obj = json.loads(raw_text.strip())
            except Exception as exc:
                parse_error = f"json_parse_error: {exc}"
                if attempt < max_attempts:
                    print(f"[A2V_PIPELINE][REFINER_VALIDATE] segment {i:02d} parse failed on attempt {attempt}: {exc}")
                    prompt = _build_repair_prompt(
                        base_prompt=prompt,
                        reason=f"Invalid JSON parse: {exc}",
                        raw_output=raw_text,
                    )
                    continue
                break

            if not isinstance(obj, dict):
                parse_error = "json_not_object"
                if attempt < max_attempts:
                    print(f"[A2V_PIPELINE][REFINER_VALIDATE] segment {i:02d} output not object on attempt {attempt}")
                    prompt = _build_repair_prompt(
                        base_prompt=prompt,
                        reason="Output is not a JSON object.",
                        raw_output=raw_text,
                    )
                    continue
                break

            is_valid, v_errors = _validate_segment_output_schema(obj)
            if is_valid:
                parsed_ok = True
                last_obj = obj
                validation_errors = []
                break

            validation_errors = v_errors
            parse_error = "schema_validation_failed"
            print(
                f"[A2V_PIPELINE][REFINER_VALIDATE] segment {i:02d} schema failed on attempt {attempt}: {v_errors}"
            )
            if attempt < max_attempts:
                prompt = _build_repair_prompt(
                    base_prompt=prompt,
                    reason="Schema validation failed.",
                    raw_output=raw_text,
                    validation_errors=v_errors,
                )
                continue
            break

        if parsed_ok and isinstance(last_obj, dict):
            output_json_path = odir / f"refiner_segment_output_{i:02d}.json"
            output_json_path.write_text(json.dumps(last_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        output_txt_path = odir / f"refiner_segment_output_{i:02d}.txt"
        output_txt_path.write_text(raw_text, encoding="utf-8")

        row = {
            "index": i,
            "prompt_file": str(prompt_file).replace("\\", "/"),
            "status_code": status_code,
            "output_txt": str(output_txt_path).replace("\\", "/"),
            "output_json": str(output_json_path).replace("\\", "/") if output_json_path else None,
            "parsed_json_ok": parsed_ok,
            "parse_error": parse_error,
            "validation_errors": validation_errors,
        }
        rows.append(row)

    report = {
        "endpoint": endpoint,
        "count": len(rows),
        "json_ok": sum(1 for r in rows if r.get("parsed_json_ok")),
        "results": rows,
    }
    report_path = odir / "refiner_segment_inference_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path).replace("\\", "/")
    return report


def _validate_segment_output_schema(obj: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    # Strict key-presence validator only (as requested).
    for key in ("canvas", "visual_timeline", "caption_track", "warnings"):
        if key not in obj:
            errors.append(f"missing_{key}")

    canvas = obj.get("canvas")
    if not isinstance(canvas, dict):
        errors.append("canvas_not_object")
    else:
        for k in ("width", "height", "fps", "duration"):
            if k not in canvas:
                errors.append(f"canvas_missing_{k}")

    vt = obj.get("visual_timeline")
    if not isinstance(vt, list):
        errors.append("visual_timeline_not_list")
    else:
        for i, row in enumerate(vt):
            if not isinstance(row, dict):
                errors.append(f"visual_timeline_{i}_not_object")
                continue
            for k in (
                "element_id",
                "source_ref",
                "type",
                "role",
                "t_start",
                "t_end",
                "layout",
                "transition_in",
                "transition_out",
                "animation",
                "audio",
                "reason",
            ):
                if k not in row:
                    errors.append(f"visual_timeline_{i}_missing_{k}")
            layout = row.get("layout")
            if not isinstance(layout, dict):
                errors.append(f"visual_timeline_{i}_layout_not_object")
            else:
                for k in ("x", "y", "width", "height", "z_index", "opacity", "fit", "caption_safe"):
                    if k not in layout:
                        errors.append(f"visual_timeline_{i}_layout_missing_{k}")
            tin = row.get("transition_in")
            if not isinstance(tin, dict):
                errors.append(f"visual_timeline_{i}_transition_in_not_object")
            else:
                for k in ("type", "duration"):
                    if k not in tin:
                        errors.append(f"visual_timeline_{i}_transition_in_missing_{k}")
            tout = row.get("transition_out")
            if not isinstance(tout, dict):
                errors.append(f"visual_timeline_{i}_transition_out_not_object")
            else:
                for k in ("type", "duration"):
                    if k not in tout:
                        errors.append(f"visual_timeline_{i}_transition_out_missing_{k}")
            anim = row.get("animation")
            if not isinstance(anim, dict):
                errors.append(f"visual_timeline_{i}_animation_not_object")
            else:
                for k in ("type", "intensity"):
                    if k not in anim:
                        errors.append(f"visual_timeline_{i}_animation_missing_{k}")

    ct = obj.get("caption_track")
    if not isinstance(ct, dict):
        errors.append("caption_track_not_object")
    else:
        for k in ("element_id", "sync_source", "layout", "style", "animation", "cues"):
            if k not in ct:
                errors.append(f"caption_track_missing_{k}")
        layout = ct.get("layout")
        if not isinstance(layout, dict):
            errors.append("caption_track_layout_not_object")
        else:
            for k in ("x", "y", "width", "height", "z_index"):
                if k not in layout:
                    errors.append(f"caption_track_layout_missing_{k}")
        style = ct.get("style")
        if not isinstance(style, dict):
            errors.append("caption_track_style_not_object")
        else:
            for k in (
                "font_family",
                "font_size_rule",
                "font_weight",
                "text_color",
                "highlight_color",
                "background_color",
                "align",
                "vertical_align",
            ):
                if k not in style:
                    errors.append(f"caption_track_style_missing_{k}")
        canim = ct.get("animation")
        if not isinstance(canim, dict):
            errors.append("caption_track_animation_not_object")
        else:
            for k in ("type", "intensity"):
                if k not in canim:
                    errors.append(f"caption_track_animation_missing_{k}")
        cues = ct.get("cues")
        if not isinstance(cues, list):
            errors.append("caption_track_cues_not_list")
        else:
            for i, cue in enumerate(cues):
                if not isinstance(cue, dict):
                    errors.append(f"caption_track_cue_{i}_not_object")
                    continue
                for k in ("index", "text", "t_start", "t_end"):
                    if k not in cue:
                        errors.append(f"caption_track_cue_{i}_missing_{k}")

    if "warnings" in obj and not isinstance(obj.get("warnings"), list):
        errors.append("warnings_not_list")
    return (len(errors) == 0, errors)


def _build_repair_prompt(
    *,
    base_prompt: str,
    reason: str,
    raw_output: str,
    validation_errors: list[str] | None = None,
) -> str:
    errs = validation_errors or []
    return (
        base_prompt
        + "\n\nYour previous output was invalid.\n"
        + f"Reason: {reason}\n"
        + (f"Validation errors: {errs}\n" if errs else "")
        + "Fix and return ONLY strict valid JSON matching the required schema.\n"
        + "No markdown. No explanation. No extra keys outside schema intent.\n"
        + f"Previous invalid output:\n{raw_output}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run refiner on all per-segment prompts one by one.")
    parser.add_argument("--prompts-dir", default="output/refiner_segment_prompts")
    parser.add_argument("--endpoint", required=True, help="Refiner endpoint URL (e.g., https://.../generate)")
    parser.add_argument("--output-dir", default="output/refiner_segment_outputs")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2400)
    parser.add_argument("--timeout-s", type=float, default=420.0)
    args = parser.parse_args()

    report = run_refiner_for_segment_prompts(
        prompts_dir=args.prompts_dir,
        endpoint=args.endpoint,
        output_dir=args.output_dir,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout_s,
    )
    print(json.dumps({"count": report["count"], "json_ok": report["json_ok"], "report_path": report["report_path"]}, indent=2))


if __name__ == "__main__":
    main()
