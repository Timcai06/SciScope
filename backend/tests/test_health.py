import re
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from backend.app.main import create_app

    return TestClient(create_app())


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in headers.items()
            ],
        }
    )


class _FakeCursor:
    def __init__(self):
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query: str) -> None:
        self.query = query

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


def test_generated_request_id_header_uses_full_uuid_hex(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    client = _client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert re.fullmatch(r"req-[0-9a-f]{32}", response.headers["x-request-id"])


def test_session_context_is_cleared_when_session_header_is_absent():
    from backend.app.core.request_context import (
        bind_request_context,
        clear_request_context,
        session_id,
    )

    bind_request_context(
        _request({"x-request-id": "req-test-1", "x-sciscope-session": " session-1 "})
    )
    assert session_id() == "session-1"

    bind_request_context(_request({"x-request-id": "req-test-2"}))

    assert session_id() == ""
    clear_request_context()


def test_request_id_header_is_returned_on_unhandled_error(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    from backend.app.main import create_app

    app = create_app()

    @app.get("/raise-test-error")
    def raise_test_error():
        raise RuntimeError("do not leak")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/raise-test-error", headers={"x-request-id": "req-error-1"})

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["x-request-id"] == "req-error-1"


def test_production_http_exception_500_is_generic(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    from backend.app.main import create_app

    app = create_app()

    @app.get("/raise-http-500")
    def raise_http_500():
        raise HTTPException(status_code=500, detail="secret detail")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/raise-http-500", headers={"x-request-id": "req-http-500"})

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["x-request-id"] == "req-http-500"
    assert "secret detail" not in response.text


def test_local_unhandled_error_raises_for_debugging(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "local")
    from backend.app.main import create_app

    app = create_app()

    @app.get("/raise-local-error")
    def raise_local_error():
        raise RuntimeError("local debug error")

    client = TestClient(app)

    with pytest.raises(RuntimeError, match="local debug error"):
        client.get("/raise-local-error")


def test_cors_exposes_request_id_header(monkeypatch):
    monkeypatch.setenv("SCISCOPE_CORS_ORIGINS", "https://example.com")
    client = _client()

    response = client.get("/healthz", headers={"Origin": "https://example.com"})

    assert response.status_code == 200
    expose_headers = response.headers["access-control-expose-headers"]
    assert "x-request-id" in {header.strip().lower() for header in expose_headers.split(",")}


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


def test_readyz_requires_retrieval_tables_in_production(monkeypatch):
    class MissingRetrievalCursor(_FakeCursor):
        def execute(self, query: str) -> None:
            if "paper_chunks" in query:
                raise RuntimeError("relation paper_chunks does not exist")
            super().execute(query)

    class MissingRetrievalConnection(_FakeConnection):
        def cursor(self):
            return MissingRetrievalCursor()

    def fake_connect(*args, **kwargs):
        return MissingRetrievalConnection()

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
    assert body["checks"]["retrieval"]["status"] == "unavailable"
    assert "paper_chunks" not in body["checks"]["retrieval"]["message"]


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
