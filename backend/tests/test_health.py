import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from backend.app.main import create_app

    return TestClient(create_app())


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query: str) -> None:
        return None

    def fetchone(self) -> tuple[int]:
        return (1,)


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor()


def _stub_ready_database(monkeypatch):
    def fake_connect(*args, **kwargs):
        return _FakeConnection()

    monkeypatch.setenv("SCISCOPE_DB_DSN", "postgresql://example.invalid/sciscope")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))


def test_healthz_does_not_require_database(monkeypatch):
    monkeypatch.setenv("SCISCOPE_APP_NAME", "SciScope")
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)
    client = _client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "SciScope"}


def test_request_id_header_is_returned(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    client = _client()

    response = client.get("/healthz", headers={"x-request-id": "req-test-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-test-1"


def test_readyz_reports_missing_database(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)
    client = _client()

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
    client = _client()

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
    client = _client()

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"]["status"] == "unavailable"
    assert body["checks"]["db"]["message"] == "database readiness probe failed"
    assert "db down" not in body["checks"]["db"]["message"]


def test_readyz_rejects_mock_llm_in_production(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "true")
    _stub_ready_database(monkeypatch)
    client = _client()

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"]["status"] == "configured"
    assert body["checks"]["model"]["status"] == "mock"


def test_readyz_reports_missing_deepseek_key(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "false")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    _stub_ready_database(monkeypatch)
    client = _client()

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"]["status"] == "configured"
    assert body["checks"]["model"]["status"] == "missing"
    assert "DEEPSEEK_API_KEY" in body["checks"]["model"]["message"]
