from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from vasp.llm.schemas import LLMModel, LLMRequest, LLMResponse


class LLMClient:
    """Dedicated Gemma HTTP client (ngrok endpoints)."""

    def __init__(self, *, e2b_url: Optional[str] = None, e4b_url: Optional[str] = None) -> None:
        _load_dotenv_if_present()
        self.e2b_url = e2b_url or _env_first("E2B_URL", "GEMMA_E2B_URL", "GEMMA_E2B_UR")
        self.e4b_url = e4b_url or _env_first("E4B_URL", "GEMMA_E4B_URL")
        self.connect_timeout_s = float(os.getenv("GEMMA_CONNECT_TIMEOUT_S", "20"))
        self.read_timeout_s = float(os.getenv("GEMMA_READ_TIMEOUT_S", os.getenv("GEMMA_TIMEOUT_S", "180")))
        self.write_timeout_s = float(os.getenv("GEMMA_WRITE_TIMEOUT_S", "20"))
        self.retries = int(os.getenv("GEMMA_RETRIES", "2"))

    def generate_text(self, req: LLMRequest) -> LLMResponse:
        url = self._url_for(req.model)
        if not url:
            raise ValueError(
                f"Missing endpoint for model '{req.model}'. "
                "Set E2B_URL/E4B_URL (or GEMMA_E2B_URL/GEMMA_E4B_URL) in .env."
            )

        payload: dict[str, Any] = {
            "prompt": req.prompt,
            "temperature": req.temperature,
        }
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens

        timeout = httpx.Timeout(
            connect=self.connect_timeout_s,
            read=self.read_timeout_s,
            write=self.write_timeout_s,
            pool=self.connect_timeout_s,
        )
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = httpx.post(url, json=payload, timeout=timeout)
                resp.raise_for_status()
                text = _extract_text(resp)
                return LLMResponse(model=req.model, text=text)
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except httpx.HTTPError as exc:
                raise RuntimeError(f"LLM request failed: {exc}") from exc

        raise RuntimeError(f"LLM request failed: {last_exc}")

    def generate_json(self, req: LLMRequest) -> dict[str, Any]:
        """Force JSON-only output; attempt repair if needed."""
        response = self.generate_text(req)
        return _parse_json_strict(response.text)

    def _url_for(self, model: LLMModel) -> str:
        raw = self.e2b_url if model == "e2b" else self.e4b_url
        return _normalize_generate_url(raw)


def _extract_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return resp.text.strip()

    if isinstance(data, dict):
        for key in ("response", "text", "output", "content"):
            if key in data and isinstance(data[key], str):
                return data[key].strip()
    return resp.text.strip()


def _normalize_generate_url(url: str) -> str:
    if not url:
        return url
    if url.endswith("/"):
        url = url[:-1]
    if url.endswith("/generate"):
        return url
    return f"{url}/generate"


def _parse_json_strict(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Simple repair: take the first/last JSON object bounds.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from LLM: {exc}") from exc
    raise ValueError("Invalid JSON from LLM.")


def _env_first(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _load_dotenv_if_present() -> None:
    """Load simple KEY=VALUE pairs from repo .env if vars are not already set."""
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
