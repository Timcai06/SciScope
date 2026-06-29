from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_healthz_does_not_require_database(monkeypatch):
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "SciScope"}


def test_readyz_reports_missing_database(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"]["status"] == "missing"
    assert "SCISCOPE_DB_DSN" in body["checks"]["db"]["message"]
