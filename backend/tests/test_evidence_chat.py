import pytest

from backend.app.core.config import get_settings
from backend.app.services.deepseek_provider import LocalOpenAIProvider, get_llm_provider
from backend.app.services.evidence_chat import answer_question
from data_pipeline.loaders import load_papers
from data_pipeline.sample_data import sample_papers_path


@pytest.fixture(autouse=True)
def _clear_db_env(monkeypatch):
    """Keep these hermetic: assert behavior over the sample corpus, not whatever
    dev PostgreSQL happens to be running. Without a DSN, ``answer_question`` uses
    the in-memory sample matcher (the path these tests pass ``papers`` for)."""
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)


class FailingProvider:
    def complete(self, prompt: str) -> str:
        raise AssertionError("provider should not be called without evidence")


class FakeHTTPResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return b'{"choices":[{"message":{"content":"local answer"}}]}'


def test_answer_question_returns_evidence():
    papers = load_papers(sample_papers_path())

    response = answer_question("What does RAG improve?", papers)

    assert "RAG" in response.answer or "retrieval" in response.answer
    assert len(response.evidence) >= 1
    assert response.confidence in {"high", "medium"}


def test_answer_question_matches_keyword_evidence():
    papers = load_papers(sample_papers_path())

    response = answer_question("knowledge graph reasoning", papers)

    titles = {item.title for item in response.evidence}
    assert "Large Language Models for Knowledge Graph Reasoning" in titles


def test_answer_question_no_evidence_returns_low_confidence():
    papers = load_papers(sample_papers_path())

    response = answer_question("unobtainium quasar flux", papers, provider=FailingProvider())

    assert response.answer == "No matching evidence found for this question in the current corpus."
    assert response.evidence == []
    assert response.confidence == "low"


def test_rag_query_prioritizes_retrieval_augmented_generation_paper():
    papers = load_papers(sample_papers_path())

    response = answer_question("rag", papers)

    assert response.evidence[0].title == "Retrieval Augmented Generation for Scientific Question Answering"


def test_deepseek_provider_requires_api_key_when_mock_disabled(monkeypatch):
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "false")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "deepseek")

    provider = get_llm_provider()

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        provider.complete("Question: test")


def test_get_llm_provider_selects_local_vllm(monkeypatch):
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "false")
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "vllm")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")

    provider = get_llm_provider()

    assert isinstance(provider, LocalOpenAIProvider)


def test_get_llm_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "false")
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "unknown")

    with pytest.raises(RuntimeError, match="Unsupported SCISCOPE_LLM_PROVIDER"):
        get_llm_provider()


def test_local_openai_provider_posts_chat_completion(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = request.data.decode("utf-8")
        return FakeHTTPResponse()

    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "false")
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "vllm")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "mlx-community/Qwen2.5-7B-Instruct-4bit")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "local-test-key")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = LocalOpenAIProvider(get_settings())
    answer = provider.complete("Question: test")

    assert answer == "local answer"
    assert captured["url"] == "http://127.0.0.1:8001/v1/chat/completions"
    assert captured["timeout"] == 120
    assert captured["headers"]["Authorization"] == "Bearer local-test-key"
    assert "mlx-community/Qwen2.5-7B-Instruct-4bit" in captured["payload"]
    assert "Question: test" in captured["payload"]
