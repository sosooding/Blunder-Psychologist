"""LLM provider seam.

One tiny ``generate(prompt) -> str`` interface behind ``LLM_PROVIDER`` so the rest of the system
never imports a vendor SDK directly. The free stack: Gemini Flash (free tier) or a fully-local
Ollama model. Both backends lazy-import their client, so core stays importable — and every test
runs against ``FakeProvider`` with no network and no API key.
"""

import logging
from typing import Protocol

import httpx

from .config import settings

logger = logging.getLogger("blunder.llm")


class LLMUnavailable(RuntimeError):
    """The configured provider's client/library is missing or unreachable."""


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> str:
        """Return the model's raw text completion for ``prompt``."""
        ...


class GeminiProvider:
    """Google Gemini Flash via the free tier. Lazy-imports ``google.generativeai``."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def generate(self, prompt: str) -> str:
        try:
            from google import genai  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise LLMUnavailable("google-genai is not installed") from exc
        client = genai.Client(api_key=self._api_key)
        resp = client.models.generate_content(model=self._model, contents=prompt)
        return resp.text


class OllamaProvider:
    """A local Ollama model — no API key, no network beyond localhost."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url

    def generate(self, prompt: str) -> str:
        resp = httpx.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["response"]


def build_provider() -> LLMProvider:
    """Construct the provider named by ``settings.llm_provider``."""
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise LLMUnavailable("LLM_PROVIDER=gemini but GEMINI_API_KEY is unset")
        return GeminiProvider(settings.gemini_api_key, settings.llm_model)
    if provider == "ollama":
        return OllamaProvider(settings.ollama_model, settings.ollama_base_url)
    raise LLMUnavailable(f"unknown LLM_PROVIDER: {settings.llm_provider!r}")
