from __future__ import annotations

from abc import ABC, abstractmethod

from vasp.core.timeline import Timeline


class Renderer(ABC):
    """Renders a Timeline to a final video artifact."""

    @abstractmethod
    def render(self, timeline: Timeline, output_uri: str) -> None:
        raise NotImplementedError
