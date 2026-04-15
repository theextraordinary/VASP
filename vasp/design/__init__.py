"""Design module for VASP."""

from vasp.design.styles import DesignStyle, TextStyle, VisualStyle
from vasp.design.presets import DesignPresetRegistry
from vasp.design.preset_map import caption_design_params, visual_design_params
from vasp.design.render_catalog import (
    BACKGROUND_PRESETS,
    FRAME_PRESETS,
    SHAPE_PRESETS,
    CAPTION_DESIGN_REFS,
    VISUAL_DESIGN_REFS,
    render_design_catalog_text,
)

__all__ = [
    "DesignStyle",
    "TextStyle",
    "VisualStyle",
    "DesignPresetRegistry",
    "caption_design_params",
    "visual_design_params",
    "BACKGROUND_PRESETS",
    "FRAME_PRESETS",
    "SHAPE_PRESETS",
    "CAPTION_DESIGN_REFS",
    "VISUAL_DESIGN_REFS",
    "render_design_catalog_text",
]
