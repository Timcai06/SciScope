import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.corpus_service import get_corpus


@pytest.fixture
def client():
    get_corpus.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_corpus.cache_clear()


def test_ingest_status_returns_ready_with_paper_count(client):
    response = client.get("/api/ingest/status")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "papers": 5}


def test_dashboard_overview_returns_sample_corpus_summary(client):
    response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_papers"] == 5
    assert payload["year_range"] == {"start": 2020, "end": 2024}
    assert len(payload["publication_trend"]) == 5
    assert len(payload["top_keywords"]) == 10


def test_chat_endpoint_returns_answer_and_evidence(client):
    response = client.post("/api/chat", json={"question": "What does RAG improve?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] == "medium"
    assert payload["evidence"]
    assert "answer" in payload


def test_chat_endpoint_returns_low_confidence_without_evidence(client):
    response = client.post("/api/chat", json={"question": "zyxwvu unmatched query"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] == "low"
    assert payload["evidence"] == []


def test_chat_endpoint_rejects_whitespace_question(client):
    response = client.post("/api/chat", json={"question": "   "})

    assert response.status_code == 422


def test_cors_allows_configured_localhost_origin(client):
    response = client.options(
        "/api/ingest/status",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
