from __future__ import annotations

from typing import Dict, Optional

from vasp.design.styles import DesignStyle


class DesignPresetRegistry:
    """In-memory registry for design presets."""

    def __init__(self) -> None:
        self._presets: Dict[str, DesignStyle] = {}

    def add(self, preset: DesignStyle) -> None:
        self._presets[preset.id] = preset

    def get(self, preset_id: str) -> Optional[DesignStyle]:
        return self._presets.get(preset_id)
