"""LLM provider abstraction used by evidence chat and agent tools.

Boundary:
  - Normalizes provider selection (`mock` / local OpenAI-compatible / deepseek).
  - Exposes a tiny `complete(prompt)` contract shared by chat services.
  - Keeps transport and decoding details inside this module; callers only handle strings.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from backend.app.core.config import Settings, get_settings


class LLMProvider(Protocol):
    """Protocol for all providers injected into higher-level services."""

    def complete(self, prompt: str) -> str:
        """Return a completion for the prompt."""


class MockDeepSeekProvider:
    """Deterministic offline fallback used in tests and no-LLM mode."""

    def complete(self, prompt: str) -> str:
        return (
            "RAG and retrieval augmented generation improve scientific question "
            "answering by grounding answers in paper evidence."
        )


class DeepSeekProvider:
    """DeepSeek cloud provider using its OpenAI-compatible chat API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def complete(self, prompt: str) -> str:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required when SCISCOPE_USE_MOCK_LLM=false")

        endpoint = self.settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are SciScope, an evidence-grounded scientific literature "
                        "analysis assistant. Answer concisely in Chinese when the user "
                        "question is Chinese, otherwise use the user's language."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DeepSeek request failed: {exc}") from exc

        return _extract_openai_message(data)


class LocalOpenAIProvider:
    """OpenAI-compatible local endpoint provider for offline/inference deployments."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def complete(self, prompt: str) -> str:
        endpoint = self.settings.local_llm_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.local_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are SciScope, an evidence-grounded scientific literature "
                        "analysis assistant. Answer concisely in Chinese when the user "
                        "question is Chinese, otherwise use the user's language."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 512,
        }
        headers = {"Content-Type": "application/json"}
        if self.settings.local_llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.local_llm_api_key}"

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Local LLM request failed: {exc}") from exc

        return _extract_openai_message(data)


def _extract_openai_message(data: dict[str, Any]) -> str:
    """Extract completion text from OpenAI chat-completion payload."""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Local LLM response did not match OpenAI chat format") from exc

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Local LLM response was empty")

    return content.strip()


def get_llm_provider() -> LLMProvider:
    """Select provider by settings, with explicit hard failure on unknown values."""
    settings = get_settings()
    if settings.use_mock_llm:
        return MockDeepSeekProvider()
    if settings.llm_provider in {"local", "vllm", "lmstudio"}:
        return LocalOpenAIProvider(settings)
    if settings.llm_provider != "deepseek":
        raise RuntimeError(f"Unsupported SCISCOPE_LLM_PROVIDER value: {settings.llm_provider!r}")
    return DeepSeekProvider(settings)
