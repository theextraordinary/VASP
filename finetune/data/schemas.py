from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Message(BaseModel):
    role: str
    content: str


class TrainingRow(BaseModel):
    messages: list[Message] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_roles(self) -> "TrainingRow":
        expected = ["system", "user", "assistant"]
        roles = [m.role for m in self.messages]
        if roles != expected:
            raise ValueError(f"Expected roles {expected}, got {roles}")
        return self
