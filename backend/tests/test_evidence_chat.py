import pytest

from backend.app.services.deepseek_provider import get_llm_provider
from backend.app.services.evidence_chat import answer_question
from data_pipeline.loaders import load_papers
from data_pipeline.sample_data import sample_papers_path


class FailingProvider:
    def complete(self, prompt: str) -> str:
        raise AssertionError("provider should not be called without evidence")


def test_answer_question_returns_evidence():
    papers = load_papers(sample_papers_path())

    response = answer_question("What does RAG improve?", papers)

    assert "RAG" in response.answer or "retrieval" in response.answer
    assert len(response.evidence) >= 1
    assert response.confidence == "medium"


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

    provider = get_llm_provider()

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        provider.complete("Question: test")
