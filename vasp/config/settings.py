from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VASP_", extra="ignore")

    gemma_e2b_endpoint: str | None = None
    gemma_e4b_endpoint: str | None = None
    gemma_timeout_seconds: float = 30.0
