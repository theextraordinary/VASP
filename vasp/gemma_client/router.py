from __future__ import annotations

from enum import Enum


class TaskComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelRouter:
    """Selects Gemma model based on task complexity."""

    def choose_model(self, complexity: TaskComplexity) -> str:
        if complexity == TaskComplexity.HIGH:
            return "gemma-e4b"
        if complexity == TaskComplexity.MEDIUM:
            return "gemma-e4b"
        return "gemma-e2b"
