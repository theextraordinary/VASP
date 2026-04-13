from __future__ import annotations

from typing import Dict, Optional, Tuple

from vasp.core.elements import Element
from vasp.core.ids import new_id
from vasp.core.timeline import Timeline, TimelineItem, Track, TrackType


class TimelineBuilder:
    """Lightweight helper for assembling timelines without extra abstractions."""

    def __init__(self, timeline_id: Optional[str] = None) -> None:
        self.timeline = Timeline(id=timeline_id or new_id("timeline"))
        self.elements: Dict[str, Element] = {}
        self._tracks: Dict[str, Track] = {}

    def add_track(self, track_type: TrackType, name: Optional[str] = None) -> str:
        track_id = new_id("track")
        track = Track(id=track_id, type=track_type, name=name)
        self._tracks[track_id] = track
        self.timeline.tracks.append(track)
        return track_id

    def add_element(self, element: Element) -> str:
        self.elements[element.id] = element
        return element.id

    def place(
        self,
        element_id: str,
        track_id: str,
        start: float,
        duration: float,
        layer: int = 0,
        trim_in: float = 0.0,
        trim_out: Optional[float] = None,
        playback_speed: float = 1.0,
    ) -> str:
        if track_id not in self._tracks:
            raise ValueError(f"Unknown track_id: {track_id}")
        item_id = new_id("item")
        item = TimelineItem(
            id=item_id,
            element_id=element_id,
            track_id=track_id,
            start=start,
            duration=duration,
            layer=layer,
            trim_in=trim_in,
            trim_out=trim_out,
            playback_speed=playback_speed,
        )
        self._tracks[track_id].items.append(item)
        return item_id

    def build(self) -> Tuple[Timeline, Dict[str, Element]]:
        # Keep timeline duration in sync with placements.
        self.timeline.duration = self.timeline.compute_duration()
        return self.timeline, self.elements
