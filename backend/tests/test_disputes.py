"""The dispute frontier must remain read-only and evidence-qualified."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.app.agent.tools import list_disputes
from backend.app.main import create_app


def test_disputes_api_maps_store_rows(monkeypatch) -> None:
    from backend.app.api import routes_disputes

    monkeypatch.setattr(
        routes_disputes,
        "disputed_claims",
        lambda limit: [{"claim": "咖啡降低心脏病风险", "support_count": 2, "contradict_count": 1, "paper_count": 3, "paper_ids": ["P1", "P2", "P3"], "last_seen": "2026-08-04"}],
    )
    response = TestClient(create_app()).get("/api/disputes?limit=10")
    assert response.status_code == 200
    assert response.json()["disputes"][0]["contradict_count"] == 1
    assert response.json()["disputes"][0]["paper_ids"] == ["P1", "P2", "P3"]


def test_disputes_tool_clamps_limit_and_exposes_boundary(monkeypatch) -> None:
    monkeypatch.setattr(list_disputes, "disputed_claims", lambda limit: [] if limit == 100 else (_ for _ in ()).throw(AssertionError(limit)))
    payload = json.loads(list_disputes.run({"limit": 999}))
    assert payload["争议数量"] == 0
    assert "可核验" in payload["边界"]
