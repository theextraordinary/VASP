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
    planner_output_path: str | Path | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2400,
    timeout_s: float = 420.0,
    max_attempts: int = 5,
    enable_validation: bool = True,
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

    planner_segments = _load_planner_segments(planner_output_path)
    rows: list[dict[str, Any]] = []
    for i, prompt_file in enumerate(prompt_files, start=1):
        base_prompt = prompt_file.read_text(encoding="utf-8")
        prompt = base_prompt
        status_code = 0
        raw_text = ""
        parsed_ok = False
        parse_error = None
        output_json_path = None
        validation_errors: list[str] = []
        last_obj: dict[str, Any] | None = None
        segment_ctx = planner_segments[i - 1] if i - 1 < len(planner_segments) else None

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

            if not enable_validation:
                parsed_ok = True
                last_obj = obj
                validation_errors = []
                break
            is_valid, v_errors = _validate_segment_output_schema(obj, segment_ctx=segment_ctx)
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
                    base_prompt=base_prompt,
                    reason="Schema validation failed.",
                    raw_output=raw_text,
                    validation_errors=v_errors,
                    segment_ctx=segment_ctx,
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


def _validate_segment_output_schema(
    obj: dict[str, Any],
    *,
    segment_ctx: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
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
    _validate_numeric_and_timing_semantics(obj, errors, segment_ctx=segment_ctx)
    return (len(errors) == 0, errors)


def _validate_numeric_and_timing_semantics(
    obj: dict[str, Any],
    errors: list[str],
    *,
    segment_ctx: dict[str, Any] | None = None,
) -> None:
    canvas = obj.get("canvas") if isinstance(obj.get("canvas"), dict) else {}
    cw = _to_float(canvas.get("width"), 0.0)
    ch = _to_float(canvas.get("height"), 0.0)
    seg_start = _to_float((segment_ctx or {}).get("t_start"), None)
    seg_end = _to_float((segment_ctx or {}).get("t_end"), None)
    vt = obj.get("visual_timeline") if isinstance(obj.get("visual_timeline"), list) else []

    used_ids: set[str] = set()
    for i, row in enumerate(vt):
        if not isinstance(row, dict):
            continue
        eid = str(row.get("element_id") or "").strip()
        if eid:
            used_ids.add(eid)
        rs = _to_float(row.get("t_start"), None)
        re = _to_float(row.get("t_end"), None)
        if rs is None or re is None or re <= rs:
            errors.append(f"visual_timeline_{i}_invalid_timing")
        if seg_start is not None and rs is not None and rs < seg_start - 1e-3:
            errors.append(f"visual_timeline_{i}_starts_before_segment")
        if seg_end is not None and re is not None and re > seg_end + 1e-3:
            errors.append(f"visual_timeline_{i}_ends_after_segment")

        layout = row.get("layout")
        if isinstance(layout, dict):
            x = _to_float(layout.get("x"), None)
            y = _to_float(layout.get("y"), None)
            w = _to_float(layout.get("width"), None)
            h = _to_float(layout.get("height"), None)
            o = _to_float(layout.get("opacity"), None)
            if None not in (x, y, w, h):
                if x < 0 or y < 0 or w <= 0 or h <= 0:
                    errors.append(f"visual_timeline_{i}_layout_invalid_bounds")
                if cw > 0 and x + w > cw + 1e-3:
                    errors.append(f"visual_timeline_{i}_layout_exceeds_canvas_width")
                if ch > 0 and y + h > ch + 1e-3:
                    errors.append(f"visual_timeline_{i}_layout_exceeds_canvas_height")
            if o is not None and (o < 0.0 or o > 1.0):
                errors.append(f"visual_timeline_{i}_layout_opacity_out_of_range")

    caption_track = obj.get("caption_track")
    if isinstance(caption_track, dict):
        layout = caption_track.get("layout")
        if isinstance(layout, dict):
            lx = _to_float(layout.get("x"), None)
            ly = _to_float(layout.get("y"), None)
            lw = _to_float(layout.get("width"), None)
            lh = _to_float(layout.get("height"), None)
            if None not in (lx, ly, lw, lh):
                if lx < 0 or ly < 0 or lw <= 0 or lh <= 0:
                    errors.append("caption_track_layout_invalid_bounds")
                if cw > 0 and lx + lw > cw + 1e-3:
                    errors.append("caption_track_layout_exceeds_canvas_width")
                if ch > 0 and ly + lh > ch + 1e-3:
                    errors.append("caption_track_layout_exceeds_canvas_height")
                # Readability baseline: ensure caption region is not tiny.
                if cw > 0 and lw < 0.2 * cw:
                    errors.append("caption_track_layout_too_narrow_for_readability")
                if ch > 0 and lh < 0.05 * ch:
                    errors.append("caption_track_layout_too_short_for_readability")
        style = caption_track.get("style")
        if isinstance(style, dict):
            font_weight = _to_float(style.get("font_weight"), None)
            if font_weight is not None and font_weight < 300:
                errors.append("caption_track_style_font_weight_too_low_for_readability")
            for color_key in ("text_color", "highlight_color", "background_color"):
                if color_key in style and not _is_color_like(style.get(color_key)):
                    errors.append(f"caption_track_style_invalid_{color_key}")
        cues = caption_track.get("cues")
        if isinstance(cues, list):
            expected_cue_count = _segment_expected_cue_count(segment_ctx)
            if expected_cue_count is not None and len(cues) != expected_cue_count:
                errors.append(
                    f"caption_track_cues_count_mismatch_expected_{expected_cue_count}_got_{len(cues)}"
                )
            prev_end: float | None = None
            for i, cue in enumerate(cues):
                if not isinstance(cue, dict):
                    continue
                cs = _to_float(cue.get("t_start"), None)
                ce = _to_float(cue.get("t_end"), None)
                ctext = str(cue.get("text") or "").strip()
                if not ctext:
                    errors.append(f"caption_track_cue_{i}_empty_text")
                if cs is None or ce is None or ce <= cs:
                    errors.append(f"caption_track_cue_{i}_invalid_timing")
                    continue
                if prev_end is not None and cs + 1e-3 < prev_end:
                    errors.append(f"caption_track_cue_{i}_overlaps_previous")
                prev_end = ce
                if seg_start is not None and cs < seg_start - 1e-3:
                    errors.append(f"caption_track_cue_{i}_starts_before_segment")
                if seg_end is not None and ce > seg_end + 1e-3:
                    errors.append(f"caption_track_cue_{i}_ends_after_segment")

    if segment_ctx:
        candidate_ids = {
            str(c.get("element_id")).strip()
            for c in (segment_ctx.get("visual_candidates") or [])
            if isinstance(c, dict) and c.get("element_id")
        }
        if candidate_ids and used_ids and not (candidate_ids & used_ids):
            errors.append("visual_timeline_no_match_with_planner_visual_candidates")


def _build_repair_prompt(
    *,
    base_prompt: str,
    reason: str,
    raw_output: str,
    validation_errors: list[str] | None = None,
    segment_ctx: dict[str, Any] | None = None,
) -> str:
    errs = validation_errors or []
    segment_hint = ""
    if segment_ctx:
        segment_hint = (
            "Planner segment requirements (must align exactly):\n"
            + json.dumps(segment_ctx, ensure_ascii=False, indent=2)
            + "\n"
        )
    return (
        base_prompt
        + "\n\nYour previous output was invalid.\n"
        + f"Reason: {reason}\n"
        + (f"Validation errors: {errs}\n" if errs else "")
        + segment_hint
        + "Ensure object placement, timing, size, color and style properties are internally valid and consistent with this planner segment.\n"
        + "Ensure captions are readable (reasonable caption box sizing and legible style) and synced (valid, ordered cue timings).\n"
        + "All visual and caption cue timings must remain inside this segment window.\n"
        + "Use planner visual_candidates; avoid unrelated element_ids.\n"
        + "Fix and return ONLY strict valid JSON matching the required schema.\n"
        + "No markdown. No explanation. No extra keys outside schema intent.\n"
        + f"Previous invalid output:\n{raw_output}\n"
    )


def _load_planner_segments(planner_output_path: str | Path | None) -> list[dict[str, Any]]:
    if not planner_output_path:
        return []
    path = Path(planner_output_path)
    if not path.exists() or not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return []
    if not isinstance(obj, dict):
        return []
    segs = obj.get("segments")
    if not isinstance(segs, list):
        return []
    return [s for s in segs if isinstance(s, dict)]


def _to_float(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def _is_color_like(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip().lower()
    if not s:
        return False
    if s.startswith("#") and len(s) in {4, 7, 9}:
        return True
    if s.startswith("rgb(") or s.startswith("rgba("):
        return True
    # allow named CSS-like colors
    return s.isalpha()


def _segment_expected_cue_count(segment_ctx: dict[str, Any] | None) -> int | None:
    if not segment_ctx:
        return None
    ci = segment_ctx.get("caption_indices")
    if not isinstance(ci, list):
        return None
    valid = [x for x in ci if isinstance(x, int)]
    if not valid:
        return None
    return len(valid)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run refiner on all per-segment prompts one by one.")
    parser.add_argument("--prompts-dir", default="output/refiner_segment_prompts")
    parser.add_argument("--endpoint", required=True, help="Refiner endpoint URL (e.g., https://.../generate)")
    parser.add_argument("--output-dir", default="output/refiner_segment_outputs")
    parser.add_argument("--planner-output", default=None, help="Optional planner_output.txt/json path for segment alignment checks.")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2400)
    parser.add_argument("--timeout-s", type=float, default=420.0)
    parser.add_argument("--max-attempts", type=int, default=5, help="Max retries per segment when validation fails.")
    parser.add_argument("--disable-validation", action="store_true", help="Disable schema/alignment validation and accept first valid JSON object.")
    args = parser.parse_args()

    report = run_refiner_for_segment_prompts(
        prompts_dir=args.prompts_dir,
        endpoint=args.endpoint,
        output_dir=args.output_dir,
        planner_output_path=args.planner_output,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout_s,
        max_attempts=args.max_attempts,
        enable_validation=not bool(args.disable_validation),
    )
    print(json.dumps({"count": report["count"], "json_ok": report["json_ok"], "report_path": report["report_path"]}, indent=2))


if __name__ == "__main__":
    main()
