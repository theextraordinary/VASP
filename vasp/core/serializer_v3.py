from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ANIMATION_OPTIONS = ["fade in/out", "jump in/out", "roll in/out"]


def serialize_element3_from_media_json(
    media_json: dict[str, Any],
    *,
    animation_options: list[str] | None = None,
    media_understanding_text: str | None = None,
) -> dict[str, Any]:
    """Build element3 payload from media.json using media_understanding-style properties."""
    anim_opts = animation_options or DEFAULT_ANIMATION_OPTIONS
    ctx = media_json.get("media_context", {}) if isinstance(media_json, dict) else {}
    inputs = ctx.get("inputs", []) if isinstance(ctx, dict) else []
    probe = ctx.get("probe", {}) if isinstance(ctx, dict) else {}
    analysis = ctx.get("analysis", {}) if isinstance(ctx, dict) else {}

    elements: list[dict[str, Any]] = []
    transcript_groups = _extract_caption_groups(analysis)
    if transcript_groups:
        c_start = float(transcript_groups[0].get("start", 0.0))
        c_end = float(transcript_groups[-1].get("end", c_start))
        caption_text = " ".join(str(g.get("text", "")).strip() for g in transcript_groups).strip()
        elements.append(
            {
                "element_id": "caption_track_1",
                "type": "Caption Track",
                "start_time": round(c_start, 3),
                "end_time": round(c_end, 3),
                "animation_options": anim_opts,
                "size": {"width": 900, "height": 260},
                "x": 540,
                "y": 1660,
                "time_mapping": transcript_groups,
                "text": caption_text,
            }
        )

    audio_seen = 0
    for item in inputs:
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("id", "")).strip()
        if not media_id:
            continue
        p = probe.get(media_id, {}) if isinstance(probe, dict) else {}
        about = item.get("about")
        aim = item.get("aim")
        media_type = str(item.get("media_type", "")).lower()
        path = item.get("path")
        duration = _f(p.get("duration"), 0.0)
        width = _f(p.get("width"), None)
        height = _f(p.get("height"), None)
        end_time = round(duration, 3) if duration > 0 else None

        base = {
            "element_id": f"{media_id}",
            "source_path": path,
            "about": about,
            "aim": aim,
            "start_time": 0.0,
            "end_time": end_time,
            "animation_options": anim_opts,
        }

        if media_type in {"audio", "music", "sfx"}:
            audio_seen += 1
            row = {
                **base,
                "type": "Audio",
                "volume": 1.0,
                "fade_in": 0.0,
                "fade_out": 0.0,
                "role": "main_audio" if audio_seen == 1 else "audio_layer",
            }
            elements.append(row)
            continue

        if media_type == "image":
            row = {
                **base,
                "type": "Image",
                "size": {"width": width, "height": height},
                "x": 540,
                "y": 960,
            }
            elements.append(row)
            continue

        if media_type == "gif":
            about_text = str(about or "").lower()
            is_sticker = "sticker" in about_text
            row = {
                **base,
                "type": "Sticker" if is_sticker else "GIF",
                "size": {"width": width, "height": height},
                "x": 540,
                "y": 960,
                "loop": True,
            }
            elements.append(row)
            continue

        if media_type == "video":
            row = {
                **base,
                "type": "No Audio Video Clips",
                "size": {"width": width, "height": height},
                "x": 540,
                "y": 960,
                "trim_in": 0.0,
                "trim_out": end_time,
            }
            elements.append(row)
            continue

    out = {
        "version": "3.0",
        "source": "media.json",
        "animation_options_global": anim_opts,
        "elements": elements,
    }
    if isinstance(media_understanding_text, str) and media_understanding_text.strip():
        out["media_understanding_text"] = media_understanding_text.strip()
    return out


def write_element3_txt_from_media_json(
    *,
    media_json_path: str | Path,
    output_path: str | Path = "output/element3.txt",
    animation_options: list[str] | None = None,
    media_understanding_md_path: str | Path | None = "output/media_understanding.md",
) -> Path:
    media_path = Path(media_json_path)
    if not media_path.exists():
        raise FileNotFoundError(f"media json not found: {media_path}")
    payload = json.loads(media_path.read_text(encoding="utf-8"))
    understanding_text: str | None = None
    if media_understanding_md_path:
        p = Path(media_understanding_md_path)
        if p.exists() and p.is_file():
            understanding_text = p.read_text(encoding="utf-8", errors="ignore")
    element3 = serialize_element3_from_media_json(
        payload,
        animation_options=animation_options,
        media_understanding_text=understanding_text,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_build_element3_text_document(element3), encoding="utf-8")
    return out


def _extract_caption_groups(analysis: Any) -> list[dict[str, Any]]:
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
                        "start": round(_f(g.get("start"), 0.0), 3),
                        "end": round(_f(g.get("end"), 0.0), 3),
                    }
                )
            if out:
                return out
    return []


def _f(v: Any, default: float | None) -> float | None:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _build_element3_text_document(element3: dict[str, Any]) -> str:
    base = str(element3.get("media_understanding_text", "") or "").rstrip()
    elements = element3.get("elements", [])
    if not isinstance(elements, list):
        elements = []
    lines: list[str] = []
    if base:
        lines.append(base)
        lines.append("")

    for row in elements:
        if not isinstance(row, dict):
            continue
        et = str(row.get("type", "Unknown")).strip()
        eid = str(row.get("element_id", "")).strip()
        lines.append(f"{et} -> {eid}")
        lines.append("{")
        for k in _ordered_keys_for_type(et):
            if k not in row:
                continue
            val = row.get(k)
            lines.append(f"    {k}: {_fmt_value(val)}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _ordered_keys_for_type(element_type: str) -> list[str]:
    t = element_type.lower()
    if t == "caption track":
        return [
            "element_id",
            "type",
            "start_time",
            "end_time",
            "animation_options",
            "size",
            "x",
            "y",
            "time_mapping",
            "text",
        ]
    if t == "image":
        return [
            "element_id",
            "type",
            "start_time",
            "end_time",
            "animation_options",
            "size",
            "x",
            "y",
            "about",
            "aim",
            "source_path",
        ]
    if t == "audio":
        return [
            "element_id",
            "type",
            "start_time",
            "end_time",
            "volume",
            "fade_in",
            "fade_out",
            "role",
            "about",
            "aim",
            "source_path",
            "animation_options",
        ]
    if t == "sticker":
        return [
            "element_id",
            "type",
            "start_time",
            "end_time",
            "animation_options",
            "size",
            "x",
            "y",
            "about",
            "aim",
            "source_path",
        ]
    if t == "gif":
        return [
            "element_id",
            "type",
            "start_time",
            "end_time",
            "animation_options",
            "size",
            "x",
            "y",
            "loop",
            "about",
            "aim",
            "source_path",
        ]
    if t == "no audio video clips":
        return [
            "element_id",
            "type",
            "start_time",
            "end_time",
            "animation_options",
            "size",
            "x",
            "y",
            "trim_in",
            "trim_out",
            "about",
            "aim",
            "source_path",
        ]
    return list(
        {
            "element_id",
            "type",
            "start_time",
            "end_time",
            "animation_options",
            "size",
            "x",
            "y",
            "about",
            "aim",
            "source_path",
        }
    )


def _fmt_value(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, str):
        return v
    return str(v)


def main() -> None:
    parser = argparse.ArgumentParser(description="serializer_v3: media.json -> element3.txt")
    parser.add_argument("--media-json", default="output/media.json")
    parser.add_argument("--output", default="output/element3.txt")
    parser.add_argument("--media-understanding-md", default="output/media_understanding.md")
    args = parser.parse_args()

    out = write_element3_txt_from_media_json(
        media_json_path=args.media_json,
        output_path=args.output,
        media_understanding_md_path=args.media_understanding_md,
    )
    print(out)


if __name__ == "__main__":
    main()
