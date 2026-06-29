import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_healthz_does_not_require_database(monkeypatch):
    monkeypatch.setenv("SCISCOPE_APP_NAME", "SciScope")
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "SciScope"}


def test_readyz_reports_missing_database(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"]["status"] == "missing"
    assert "SCISCOPE_DB_DSN" in body["checks"]["db"]["message"]


def test_readyz_allows_local_sample_mock_mode(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "local")
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "true")
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["db"]["status"] == "sample"
    assert body["checks"]["model"]["status"] == "mock"


def test_readyz_reports_unavailable_database(monkeypatch):
    def fake_connect(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.setenv("SCISCOPE_DB_DSN", "postgresql://example.invalid/sciscope")
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "false")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"]["status"] == "unavailable"
