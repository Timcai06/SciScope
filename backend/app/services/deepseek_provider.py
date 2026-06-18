from typing import Protocol

from backend.app.core.config import Settings, get_settings


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a completion for the prompt."""


class MockDeepSeekProvider:
    def complete(self, prompt: str) -> str:
        return (
            "RAG and retrieval augmented generation improve scientific question "
            "answering by grounding answers in paper evidence."
        )


class DeepSeekProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def complete(self, prompt: str) -> str:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required when SCISCOPE_USE_MOCK_LLM=false")

        raise RuntimeError("Real DeepSeek HTTP call is implemented in the API integration task")


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.use_mock_llm:
        return MockDeepSeekProvider()
    return DeepSeekProvider(settings)
