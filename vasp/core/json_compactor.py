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
    """Write a compact text snapshot for unified element JSON."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    compact_element = _drop_nulls(element_json)
    element_txt = out_dir / output_filename
    element_txt.write_text(_minified_json(compact_element), encoding="utf-8")
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
