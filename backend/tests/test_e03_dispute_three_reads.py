"""E03 engineering fixture: one persisted claim, then three identical reads.

This is deliberately offline and deterministic.  It proves the contract around
the database-shaped dispute row, not whether the stance judge is scientifically
accurate.  A separately captured local/live PostgreSQL trace is still required
before calling the E03 acceptance evidence complete.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app import mcp_server
from backend.app.agent.tools import list_disputes, verify_claim
from backend.app.main import create_app
from backend.app.services.stance import judge as stance_judge
from backend.app.services.stance import store as stance_store

CLAIM = "咖啡能降低心脏病风险"
PAPER_IDS = ["E03-SUPPORT", "E03-CONTRADICT"]


class _FakeEmbedder:
    def encode_query(self, _text: str) -> list[float]:
        return [1.0, 0.0]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [[0.95 if "lower" in text else 0.90, math.sqrt(1 - (0.95 if "lower" in text else 0.90) ** 2)] for text in texts]


def _drive_verify() -> dict:
    run = verify_claim.run({"claim": CLAIM, "persist": True})
    try:
        while True:
            next(run)
    except StopIteration as stop:
        return json.loads(stop.value)


def test_e03_one_persisted_canonical_claim_has_identical_api_tool_and_mcp_reads(monkeypatch) -> None:
    """One persist=true call creates both stances under one canonical claim."""
    from backend.app.api import routes_disputes
    from backend.app.services import retrieval_service
    from src.models import embeddings

    monkeypatch.setattr(
        retrieval_service,
        "search",
        lambda _query, limit=6: [
            SimpleNamespace(
                paper_id=PAPER_IDS[0], title="Support paper", year=2023,
                snippet="Coffee intake was associated with lower cardiovascular risk.",
            ),
            SimpleNamespace(
                paper_id=PAPER_IDS[1], title="Contradict paper", year=2022,
                snippet="Coffee intake was associated with higher cardiovascular risk.",
            ),
        ],
    )
    monkeypatch.setattr(embeddings, "get_embedder", lambda *_args: _FakeEmbedder())
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda _claim, _texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[
                stance_judge.EvidenceJudgement("SUPPORT", 0.95, "Coffee intake was associated with lower cardiovascular risk.", None),
                stance_judge.EvidenceJudgement("CONTRADICT", 0.90, "Coffee intake was associated with higher cardiovascular risk.", None),
            ],
        ),
    )

    persisted: dict[str, dict] = {}

    def record_once(claim: str, verdict: str, evidence: list[dict]) -> int:
        norm = stance_store.normalize_claim(claim)
        assert norm == stance_store.normalize_claim(CLAIM)
        assert verdict == "存在争议"
        assert {row["立场"] for row in evidence} == {"SUPPORT", "CONTRADICT"}
        assert [row["paper_id"] for row in evidence] == PAPER_IDS
        persisted[norm] = {
            "claim": claim,
            "support_count": 1,
            "contradict_count": 1,
            "paper_count": 2,
            "paper_ids": [row["paper_id"] for row in evidence],
            "last_seen": "fixture-2026-08-10",
        }
        return len(evidence)

    def read_disputes(limit: int = 20) -> list[dict]:
        row = persisted.get(stance_store.normalize_claim(CLAIM))
        return [row] if row else []

    monkeypatch.setattr(stance_store, "record_stances", record_once)
    monkeypatch.setattr(routes_disputes, "disputed_claims", read_disputes)
    monkeypatch.setattr(list_disputes, "disputed_claims", read_disputes)
    monkeypatch.setattr(mcp_server, "disputed_claims", read_disputes)

    written = _drive_verify()
    assert written["支持等级"] == "存在争议"
    assert written["资产写入"] == {"状态": "已写入", "记录数": 2}

    db_row = persisted[stance_store.normalize_claim(CLAIM)]
    api_row = TestClient(create_app()).get("/api/disputes?limit=20").json()["disputes"][0]
    tool_row = json.loads(list_disputes.run({"limit": 20}))["争议"][0]
    resource_row = json.loads(asyncio.run(mcp_server._read_resource("sciscope://disputes/recent"))[0].text)["disputes"][0]

    for row in (api_row, tool_row, resource_row):
        assert row["claim"] == db_row["claim"] == CLAIM
        assert row["paper_ids"] == db_row["paper_ids"] == PAPER_IDS
        assert row["support_count"] == row["contradict_count"] == 1


def test_e03_schema_exposes_aggregated_paper_ids() -> None:
    schema = open("infra/postgres/stance.sql", encoding="utf-8").read()
    assert "array_agg(DISTINCT paper_id ORDER BY paper_id) AS paper_ids" in schema
    assert schema.index("max(created_at) AS last_seen") < schema.index(
        "array_agg(DISTINCT paper_id ORDER BY paper_id) AS paper_ids"
    )


def test_e03_live_postgres_three_reads(monkeypatch) -> None:
    """Optional live gate: real PostgreSQL write plus API/tool/MCP reads.

    The scientific judgement stays deterministic so this test isolates the
    persistence and three-read contract.  It is skipped unless the caller
    explicitly provides an isolated writable database.
    """
    dsn = os.getenv("SCISCOPE_E03_LIVE_DSN")
    if not dsn:
        import pytest

        pytest.skip("set SCISCOPE_E03_LIVE_DSN to run the live PostgreSQL gate")

    import psycopg

    from backend.app.services import retrieval_service
    from src.models import embeddings

    claim = "E03 live gate coffee lowers cardiovascular risk"
    claim_norm = stance_store.normalize_claim(claim)
    monkeypatch.setenv("SCISCOPE_DB_DSN", dsn)
    monkeypatch.setattr(
        retrieval_service,
        "search",
        lambda _query, limit=6: [
            SimpleNamespace(
                paper_id=PAPER_IDS[0], title="Support paper", year=2023,
                snippet="Coffee intake was associated with lower cardiovascular risk.",
            ),
            SimpleNamespace(
                paper_id=PAPER_IDS[1], title="Contradict paper", year=2022,
                snippet="Coffee intake was associated with higher cardiovascular risk.",
            ),
        ],
    )
    monkeypatch.setattr(embeddings, "get_embedder", lambda *_args: _FakeEmbedder())
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda _claim, _texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[
                stance_judge.EvidenceJudgement(
                    "SUPPORT", 0.95,
                    "Coffee intake was associated with lower cardiovascular risk.", None,
                ),
                stance_judge.EvidenceJudgement(
                    "CONTRADICT", 0.90,
                    "Coffee intake was associated with higher cardiovascular risk.", None,
                ),
            ],
        ),
    )

    try:
        run = verify_claim.run({"claim": claim, "persist": True})
        try:
            while True:
                next(run)
        except StopIteration as stop:
            written = json.loads(stop.value)
        assert written["支持等级"] == "存在争议"
        assert written["资产写入"] == {"状态": "已写入", "记录数": 2}

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT claim, support_count, contradict_count, paper_ids "
                    "FROM contradictions WHERE claim_norm = %s",
                    (claim_norm,),
                )
                db_row = cur.fetchone()
        assert db_row is not None

        api_rows = TestClient(create_app()).get("/api/disputes?limit=100").json()["disputes"]
        tool_rows = json.loads(list_disputes.run({"limit": 100}))["争议"]
        resource_rows = json.loads(
            asyncio.run(mcp_server._read_resource("sciscope://disputes/recent"))[0].text
        )["disputes"]

        expected_ids = sorted(PAPER_IDS)
        for rows in (api_rows, tool_rows, resource_rows):
            row = next(item for item in rows if item["claim"] == claim)
            assert row["paper_ids"] == expected_ids
            assert row["support_count"] == row["contradict_count"] == 1
        assert list(db_row[3]) == expected_ids
    finally:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM claim_evidence_stance WHERE claim_norm = %s", (claim_norm,))
