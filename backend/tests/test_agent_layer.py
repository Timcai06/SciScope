"""Tests for the research-agent model layer (retrieval, trends, recommend, graph).

These stay dependency-light: pure functions are tested directly, and the
service-layer endpoints are checked for graceful degradation when the
PostgreSQL/pgvector backend and model files are unavailable.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services import graph_service, retrieval_service


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_db_env(monkeypatch):
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)


def test_fit_forecast_detects_upward_trend():
    from src.models.trends import _fit_forecast

    years = np.array([2022, 2023, 2024, 2025], dtype=float)
    values = np.array([0.01, 0.02, 0.04, 0.08])
    fc = _fit_forecast(years, values)

    assert fc["slope"] > 0
    assert fc["forecast"] >= values[-1] - 1e-9
    assert fc["low"] <= fc["forecast"] <= fc["high"]
    assert fc["next_year"] == 2026


def test_fit_forecast_handles_flat_series():
    from src.models.trends import _fit_forecast

    years = np.array([2022, 2023, 2024], dtype=float)
    values = np.array([0.05, 0.05, 0.05])
    fc = _fit_forecast(years, values)

    assert fc["slope"] == 0.0
    assert fc["forecast"] == pytest.approx(0.05)


def test_graph_ego_filter_keeps_center_neighbourhood():
    graph = {
        "type": "keyword",
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "z"}],
        "edges": [
            {"source": "a", "target": "b", "weight": 3},
            {"source": "a", "target": "c", "weight": 1},
            {"source": "b", "target": "z", "weight": 2},
        ],
    }
    ego = graph_service._ego_filter(graph, "a", limit=10)

    node_ids = {n["id"] for n in ego["nodes"]}
    assert ego["center"] == "a"
    assert node_ids == {"a", "b", "c"}
    assert all("a" in (e["source"], e["target"]) for e in ego["edges"])


def test_retrieval_unavailable_without_dsn():
    assert retrieval_service.is_available() is False
    assert retrieval_service.search("anything") == []


def test_search_endpoint_returns_503_without_backend(client):
    response = client.get("/api/search", params={"q": "graph neural network"})
    assert response.status_code == 503


def test_recommend_endpoint_returns_503_without_backend(client):
    response = client.get("/api/recommend", params={"paper_id": "X"})
    assert response.status_code == 503


def test_graph_endpoint_rejects_bad_type(client):
    response = client.get("/api/graph", params={"type": "nonsense"})
    assert response.status_code == 400
