from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class GemmaRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.3
    top_p: float = 0.9
    response_format: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional JSON schema hints for structured output."
    )


class GemmaResponse(BaseModel):
    text: str
    raw: Dict[str, Any]
