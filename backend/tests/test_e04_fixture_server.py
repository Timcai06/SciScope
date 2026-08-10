from __future__ import annotations

import json
from types import SimpleNamespace

from backend.app.agent.tools import verify_claim
from backend.app.services.stance import store as stance_store
from backend.app.mcp_server_e04_fixture import (
    FIXTURE_CLAIM,
    FIXTURE_PAPER_IDS,
    install_fixture,
)


def _run_verify(claim: str) -> dict:
    run = verify_claim.run({"claim": claim, "persist": True})
    try:
        while True:
            next(run)
    except StopIteration as stop:
        return json.loads(stop.value)


def test_e04_fixture_installs_deterministic_writeable_verify(monkeypatch) -> None:
    persisted = {}

    def record_once(claim: str, verdict: str, evidence: list[dict]) -> int:
        persisted["claim"] = claim
        persisted["verdict"] = verdict
        persisted["paper_ids"] = [row["paper_id"] for row in evidence]
        return len(evidence)

    monkeypatch.setattr(stance_store, "record_stances", record_once)
    install_fixture(monkeypatch)

    payload = _run_verify(FIXTURE_CLAIM)

    assert payload["支持等级"] == "存在争议"
    assert payload["资产写入"] == {"状态": "已写入", "记录数": 2}
    assert persisted == {
        "claim": FIXTURE_CLAIM,
        "verdict": "存在争议",
        "paper_ids": FIXTURE_PAPER_IDS,
    }


def test_e04_fixture_search_shape_is_stable(monkeypatch) -> None:
    install_fixture(monkeypatch)
    from backend.app.services import retrieval_service

    got = retrieval_service.search(FIXTURE_CLAIM, limit=6)
    assert [row.paper_id for row in got] == FIXTURE_PAPER_IDS
    assert all(isinstance(row, SimpleNamespace) for row in got)
