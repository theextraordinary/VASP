from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from vasp.animation.primitives import AnimationSpec
from vasp.core.timeline import Timeline


class AnimationEngine(ABC):
    """Applies animation specs to a timeline (pure transformations)."""

    @abstractmethod
    def apply(self, timeline: Timeline, animations: Iterable[AnimationSpec]) -> Timeline:
        raise NotImplementedError


class BasicAnimationEngine(AnimationEngine):
    """Placeholder engine; returns timeline unchanged."""

    def apply(self, timeline: Timeline, animations: Iterable[AnimationSpec]) -> Timeline:
        _ = list(animations)
        return timeline
