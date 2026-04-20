from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compact_json_outputs(
    *,
    elements_json: dict[str, Any],
    element_props_json: dict[str, Any],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write compact text snapshots with null fields removed."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    compact_elements = _drop_nulls(elements_json)
    compact_props = _drop_nulls(element_props_json)

    elements_txt = out_dir / "elements_compact.txt"
    props_txt = out_dir / "elementProps_compact.txt"

    elements_txt.write_text(_minified_json(compact_elements), encoding="utf-8")
    props_txt.write_text(_minified_json(compact_props), encoding="utf-8")
    return elements_txt, props_txt


def compact_unified_element_json(
    *,
    element_json: dict[str, Any],
    output_dir: str | Path,
    output_filename: str = "element_compact.txt",
) -> Path:
    """Write compact artifacts for unified element JSON.

    Output policy:
    - Keep only element-centric payload (`version`, `video`, `elements`, `serializer_mode`).
    - Remove heavy duplicate context blocks (`media_context`, `analysis`, etc.).
    - Write a minified json/txt compact artifact.
    - Also write a human-readable markdown snapshot with one section per element.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    normalized = _to_elements_only_payload(element_json)
    compact_element = _drop_nulls(normalized)
    element_txt = out_dir / output_filename
    element_txt.write_text(_minified_json(compact_element), encoding="utf-8")
    _write_elements_markdown(compact_element, element_txt.with_suffix(".md"))
    return element_txt


def _drop_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            reduced = _drop_nulls(item)
            if reduced is None:
                continue
            cleaned[key] = reduced
        return cleaned
    if isinstance(value, list):
        return [_drop_nulls(item) for item in value]
    return value


def _minified_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _to_elements_only_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(payload.get("version"), str):
        out["version"] = payload["version"]
    if isinstance(payload.get("video"), dict):
        out["video"] = payload["video"]
    if isinstance(payload.get("serializer_mode"), str):
        out["serializer_mode"] = payload["serializer_mode"]

    elements = payload.get("elements", [])
    slim_elements: list[dict[str, Any]] = []
    if isinstance(elements, list):
        for row in elements:
            if not isinstance(row, dict):
                continue
            slim_row: dict[str, Any] = {
                "element_id": row.get("element_id"),
                "actions": row.get("actions", []),
                "properties": row.get("properties", {}),
            }
            slim_elements.append(slim_row)
    out["elements"] = slim_elements
    return out


def _write_elements_markdown(payload: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append("# Element Compact")
    lines.append("")
    video = payload.get("video", {})
    if isinstance(video, dict):
        lines.append("## Video")
        lines.append("```json")
        lines.append(json.dumps(video, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    elements = payload.get("elements", [])
    if isinstance(elements, list):
        for idx, row in enumerate(elements, start=1):
            if not isinstance(row, dict):
                continue
            props = row.get("properties", {})
            element_type = None
            if isinstance(props, dict):
                element_type = props.get("type")
            title = f"## Element {idx}: {row.get('element_id', 'unknown')}"
            if isinstance(element_type, str) and element_type:
                title += f" ({element_type})"
            lines.append(title)
            lines.append("")
            lines.append("### Actions")
            lines.append("```json")
            lines.append(json.dumps(row.get("actions", []), ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
            lines.append("### Properties")
            lines.append("```json")
            lines.append(json.dumps(props if isinstance(props, dict) else {}, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
