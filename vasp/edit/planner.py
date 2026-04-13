from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from vasp.core.timeline import Timeline
from vasp.edit.schemas import EditPlan


class EditPlanner(ABC):
    """Produces structured edit plans from inputs."""

    @abstractmethod
    def plan(self, context: Dict[str, Any]) -> EditPlan:
        raise NotImplementedError


class RuleBasedEditPlanner(EditPlanner):
    """Placeholder planner for MVP; returns empty plan."""

    def plan(self, context: Dict[str, Any]) -> EditPlan:
        _ = context
        return EditPlan(id="plan_empty")


class PlanCompiler(ABC):
    """Turns an EditPlan into a Timeline (still non-rendered)."""

    @abstractmethod
    def compile(self, plan: EditPlan) -> Timeline:
        raise NotImplementedError
