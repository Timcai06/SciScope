from backend.app.services.evidence_chat import answer_question
from data_pipeline.loaders import load_papers
from data_pipeline.sample_data import sample_papers_path


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
