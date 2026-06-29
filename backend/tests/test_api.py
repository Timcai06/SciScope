import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.corpus_service import get_corpus


@pytest.fixture(autouse=True)
def _clear_db_env(monkeypatch):
    """Hermetic API tests run against the 5-paper sample corpus (ingest=5,
    dashboard 2020-2024); a live dev DB must not leak into the chat endpoint."""
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)


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


def test_ingest_status_prefers_database_count(monkeypatch, client):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query):
            assert query == "SELECT count(*) FROM papers"

        def fetchone(self):
            return (159187,)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return FakeCursor()

    class FakePsycopg:
        @staticmethod
        def connect(dsn):
            assert dsn == "postgresql://example/sciscope"
            return FakeConnection()

    monkeypatch.setenv("SCISCOPE_DB_DSN", "postgresql://example/sciscope")
    monkeypatch.setitem(__import__("sys").modules, "psycopg", FakePsycopg)

    response = client.get("/api/ingest/status")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "papers": 159187}


def test_ingest_status_does_not_fallback_to_sample_in_production(monkeypatch, client):
    class FakePsycopg:
        @staticmethod
        def connect(dsn):
            raise RuntimeError("db down")

    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.setenv("SCISCOPE_DB_DSN", "postgresql://example/sciscope")
    monkeypatch.setitem(__import__("sys").modules, "psycopg", FakePsycopg)

    response = client.get("/api/ingest/status")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "corpus_unavailable"


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
    assert payload["confidence"] in {"high", "medium"}
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


def test_chat_endpoint_rejects_oversized_question(monkeypatch, client):
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_QUESTION_CHARS", "5")

    response = client.post("/api/chat", json={"question": "too long"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "question_too_long"


def test_chat_endpoint_enforces_anonymous_rate_limit(monkeypatch, client):
    from backend.app.core import budget

    budget._RATE_LIMIT_BUCKETS.clear()
    monkeypatch.setenv("SCISCOPE_ANON_REQUESTS_PER_MINUTE", "1")

    first = client.post("/api/chat", json={"question": "What does RAG improve?"})
    second = client.post("/api/chat", json={"question": "What does RAG improve?"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "rate_limited"

def test_cors_allows_configured_origin(monkeypatch):
    monkeypatch.setenv("SCISCOPE_CORS_ORIGINS", "https://example.com")
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/ingest/status",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"
