from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_ingest_status_returns_ready_with_paper_count():
    response = client.get("/api/ingest/status")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "papers": 5}


def test_dashboard_overview_returns_sample_corpus_summary():
    response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_papers"] == 5
    assert payload["year_range"] == {"start": 2020, "end": 2024}
    assert len(payload["publication_trend"]) == 5
    assert len(payload["top_keywords"]) == 10


def test_chat_endpoint_returns_answer_and_evidence():
    response = client.post("/api/chat", json={"question": "What does RAG improve?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] == "medium"
    assert payload["evidence"]
    assert "answer" in payload


def test_chat_endpoint_rejects_whitespace_question():
    response = client.post("/api/chat", json={"question": "   "})

    assert response.status_code == 422
