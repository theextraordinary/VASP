from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from vasp.schemas.base import BaseSchema

LLMModel = Literal["e2b", "e4b"]


class LLMRequest(BaseSchema):
    """Generic LLM request wrapper."""

    model: LLMModel = "e2b"
    prompt: str
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: Optional[int] = None


class LLMResponse(BaseSchema):
    """Generic LLM response wrapper."""

    model: LLMModel
    text: str
