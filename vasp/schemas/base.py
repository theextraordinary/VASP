from pydantic import BaseModel


class BaseSchema(BaseModel):
    """Base schema with consistent config for the project."""

    model_config = {"extra": "forbid"}
