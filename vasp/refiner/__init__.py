"""LLM-2 refinement layer."""

from typing import Any

from vasp.refiner.schemas import InterRenderPlan
from vasp.refiner.service import refine_plan


def build_refiner_layout_input_prompt(*args: Any, **kwargs: Any):
    from vasp.refiner.layout_prompt_builder import build_refiner_layout_input_prompt as _impl

    return _impl(*args, **kwargs)


def write_refiner_layout_input_prompt(*args: Any, **kwargs: Any):
    from vasp.refiner.layout_prompt_builder import write_refiner_layout_input_prompt as _impl

    return _impl(*args, **kwargs)


def build_segmented_refiner_prompts(*args: Any, **kwargs: Any):
    from vasp.refiner.segment_prompt_builder import build_segmented_refiner_prompts as _impl

    return _impl(*args, **kwargs)


def run_refiner_for_segment_prompts(*args: Any, **kwargs: Any):
    from vasp.refiner.segment_inference_runner import run_refiner_for_segment_prompts as _impl

    return _impl(*args, **kwargs)

__all__ = [
    "InterRenderPlan",
    "refine_plan",
    "build_refiner_layout_input_prompt",
    "write_refiner_layout_input_prompt",
    "build_segmented_refiner_prompts",
    "run_refiner_for_segment_prompts",
]
