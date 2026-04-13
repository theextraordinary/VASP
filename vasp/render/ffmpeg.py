from __future__ import annotations

from vasp.core.timeline import Timeline
from vasp.render.renderer import Renderer


class FFMpegRenderer(Renderer):
    """Placeholder FFmpeg renderer; compiles timeline to FFmpeg commands later."""

    def render(self, timeline: Timeline, output_uri: str) -> None:
        _ = timeline
        _ = output_uri
        raise NotImplementedError("FFmpeg render pipeline not implemented yet.")
