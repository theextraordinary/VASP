from __future__ import annotations

from typing import Any


def expand_animation_actions(
    animation_ref: str | None,
    *,
    op: str,
    t_start: float,
    t_end: float,
    base_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Map high-level animation refs into renderer-supported action slices."""
    params = dict(base_params or {})
    name = (animation_ref or "").strip().lower()
    duration = max(0.0, t_end - t_start)
    if duration <= 0:
        return [{"t_start": t_start, "t_end": t_end, "op": op, "params": params}]

    if name in {"subtle_zoom", "zoom_in"}:
        mid = t_start + duration * 0.5
        p1 = dict(params)
        p1.setdefault("scale", 1.0)
        p2 = dict(params)
        p2["scale"] = max(float(p1.get("scale", 1.0)), 1.08)
        return [
            {"t_start": t_start, "t_end": mid, "op": op, "params": p1},
            {"t_start": mid, "t_end": t_end, "op": op, "params": p2},
        ]

    if name in {"pop", "pop_in"}:
        mid = t_start + duration * 0.2
        p1 = dict(params)
        p1["scale"] = max(float(params.get("scale", 1.0)), 1.15)
        p2 = dict(params)
        p2["scale"] = float(params.get("scale", 1.0))
        return [
            {"t_start": t_start, "t_end": mid, "op": op, "params": p1},
            {"t_start": mid, "t_end": t_end, "op": op, "params": p2},
        ]

    return [{"t_start": t_start, "t_end": t_end, "op": op, "params": params}]
