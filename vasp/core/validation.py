from __future__ import annotations

from vasp.core.timeline import Timeline


def validate_no_overlap(timeline: Timeline) -> None:
    """Ensure items on the same track and layer do not overlap in time."""
    for track in timeline.tracks:
        by_layer: dict[int, list[tuple[float, float]]] = {}
        for item in track.items:
            by_layer.setdefault(item.layer, []).append((item.start, item.end))
        for layer, windows in by_layer.items():
            windows.sort(key=lambda w: w[0])
            for idx in range(1, len(windows)):
                prev_end = windows[idx - 1][1]
                curr_start = windows[idx][0]
                if curr_start < prev_end:
                    raise ValueError(f"Overlap on track {track.id}, layer {layer}")


def validate_timeline(timeline: Timeline) -> None:
    validate_no_overlap(timeline)
