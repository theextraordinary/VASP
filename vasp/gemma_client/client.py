from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from vasp.config.settings import Settings
from vasp.gemma_client.schemas import GemmaRequest, GemmaResponse
from vasp.utils.errors import ModelAPIError
from vasp.utils.retry import retry


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Heuristic: find first JSON object in text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class GemmaClient:
    """HTTP client for Gemma endpoints exposed via ngrok URLs."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or Settings()

    @retry()
    def generate(self, request: GemmaRequest, model: str) -> GemmaResponse:
        endpoint = self._resolve_endpoint(model)
        if not endpoint:
            raise ModelAPIError(f"Missing endpoint for model: {model}")

        payload = request.model_dump()
        try:
            with httpx.Client(timeout=self.settings.gemma_timeout_seconds) as client:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelAPIError(str(exc)) from exc

        raw = response.json()
        text = raw.get("text") or raw.get("output") or ""
        return GemmaResponse(text=text, raw=raw)

    def generate_json(self, request: GemmaRequest, model: str) -> Dict[str, Any]:
        response = self.generate(request, model)
        data = _extract_json(response.text)
        if data is None:
            raise ModelAPIError("Model returned malformed JSON.")
        return data

    def _resolve_endpoint(self, model: str) -> Optional[str]:
        if model == "gemma-e2b":
            return self.settings.gemma_e2b_endpoint
        if model == "gemma-e4b":
            return self.settings.gemma_e4b_endpoint
        return None
