from __future__ import annotations

from typing import Any, Dict, Optional

from vasp.edit.planner import EditPlanner, PlanCompiler
from vasp.core.timeline import Timeline


class V2VPipeline:
    """Coordinates Video-to-Video workflow using planner + compiler."""

    def __init__(self, planner: EditPlanner, compiler: PlanCompiler) -> None:
        self.planner = planner
        self.compiler = compiler

    def run(self, video_uri: str, context: Optional[Dict[str, Any]] = None) -> Timeline:
        ctx = {"video_uri": video_uri}
        if context:
            ctx.update(context)
        plan = self.planner.plan(ctx)
        return self.compiler.compile(plan)
