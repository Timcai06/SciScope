"""Stance persistence — verify_claim's judgements accumulated as an asset.

Roadmap Step 2 (矛盾即资产): every stance-judged verify_claim run appends its
per-evidence labels to ``claim_evidence_stance``; the ``contradictions`` view
(infra/postgres/stance.sql) derives claims where the literature disagrees —
the seed of the 科学争议地图.

This is an internal, append-only sink, not a model-invokable write tool: the
agent's tool contract stays read-only (the corpus tables are never touched),
and persistence is strictly fail-open — any DB problem is swallowed so the
user still gets their answer. Rows are keyed (claim_norm, paper_id) with
last-write-wins, so re-verifying a claim refreshes stances instead of
inflating counts.
"""

from __future__ import annotations

import re
from typing import Any

_UPSERT_SQL = """
INSERT INTO claim_evidence_stance
    (claim, claim_norm, paper_id, paper_title, paper_year, stance, similarity, verdict)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (claim_norm, paper_id) DO UPDATE SET
    claim = EXCLUDED.claim,
    paper_title = EXCLUDED.paper_title,
    paper_year = EXCLUDED.paper_year,
    stance = EXCLUDED.stance,
    similarity = EXCLUDED.similarity,
    verdict = EXCLUDED.verdict,
    created_at = now()
"""

_DISPUTED_SQL = """
SELECT claim, support_count, contradict_count, paper_count, last_seen
FROM contradictions
ORDER BY last_seen DESC
LIMIT %s
"""


def normalize_claim(claim: str) -> str:
    """Fold case/whitespace/punctuation so rewordings of a claim group together."""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z一-鿿]+", " ", (claim or "").lower())).strip()


def _connect():
    from backend.app.core.config import get_settings

    import psycopg

    dsn = get_settings().db_dsn
    if not dsn:
        return None
    return psycopg.connect(dsn)


def record_stances(claim: str, verdict: str, evidence: list[dict[str, Any]]) -> int:
    """Persist one stance-judged verify_claim run; returns rows written (0 on failure).

    ``evidence`` rows carry paper_id/标题/年份/接地相似度/立场 as built by
    verify_claim. Rows without a stance label (similarity fallback) are skipped.
    Fail-open by design: persistence must never break the answer path.
    """
    rows = [
        (
            claim,
            normalize_claim(claim),
            str(e.get("paper_id")),
            str(e.get("标题") or ""),
            e.get("年份"),
            e.get("立场"),
            e.get("接地相似度"),
            verdict,
        )
        for e in evidence
        if e.get("paper_id") and e.get("立场")
    ]
    if not rows:
        return 0
    try:
        conn = _connect()
        if conn is None:
            return 0
        with conn:
            with conn.cursor() as cur:
                cur.executemany(_UPSERT_SQL, rows)
        conn.close()
        return len(rows)
    except Exception:  # noqa: BLE001 — persistence is best-effort telemetry
        return 0


def disputed_claims(limit: int = 20) -> list[dict[str, Any]]:
    """Read the contradictions view (争议地图), most recently seen first."""
    try:
        conn = _connect()
        if conn is None:
            return []
        with conn:
            with conn.cursor() as cur:
                cur.execute(_DISPUTED_SQL, (limit,))
                rows = cur.fetchall()
        conn.close()
    except Exception:  # noqa: BLE001
        return []
    return [
        {
            "claim": r[0],
            "support_count": r[1],
            "contradict_count": r[2],
            "paper_count": r[3],
            "last_seen": str(r[4]),
        }
        for r in rows
    ]
