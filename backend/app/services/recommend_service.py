"""Query-time paper recommendation over the pgvector service layer.

Given a seed paper, finds semantic neighbours via ``paper_embeddings`` and
re-ranks them by fusing semantic similarity with keyword overlap, author
overlap, and recency. Every recommendation carries explanation factors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.core.config import get_settings

CANDIDATE_POOL = 50
W_SEMANTIC = 0.6
W_KEYWORD = 0.2
W_AUTHOR = 0.1
W_RECENCY = 0.1
MMR_LAMBDA = 0.7  # relevance vs diversity trade-off for the final selection


@dataclass
class Recommendation:
    paper_id: str
    title: str
    year: int | None
    field: str
    score: float
    semantic_similarity: float
    shared_keywords: list[str] = field(default_factory=list)
    shared_authors: list[str] = field(default_factory=list)
    factors: dict[str, float] = field(default_factory=dict)


def _connect():
    import psycopg

    return psycopg.connect(get_settings().db_dsn)


def is_available() -> bool:
    settings = get_settings()
    if not settings.db_dsn:
        return False
    try:
        import psycopg  # noqa: F401

        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('paper_embeddings')")
            return cur.fetchone()[0] is not None
    except Exception:
        return False


def _resolve_paper_uid(cur, paper_id: str) -> str | None:
    cur.execute(
        """
        SELECT paper_uid FROM papers
        WHERE paper_uid = %(id)s OR source_id = %(id)s OR metadata->>'paper_id' = %(id)s
        LIMIT 1
        """,
        {"id": paper_id},
    )
    row = cur.fetchone()
    return row[0] if row else None


def recommend(paper_id: str, limit: int = 10) -> list[Recommendation]:
    if not get_settings().db_dsn:
        return []
    from pgvector.psycopg import register_vector

    with _connect() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            seed_uid = _resolve_paper_uid(cur, paper_id)
            if not seed_uid:
                return []

            # Seed features.
            cur.execute("SELECT embedding FROM paper_embeddings WHERE paper_uid = %s", (seed_uid,))
            seed_row = cur.fetchone()
            if not seed_row:
                return []
            seed_vec = seed_row[0]
            cur.execute("SELECT year FROM papers WHERE paper_uid = %s", (seed_uid,))
            seed_year = cur.fetchone()[0]
            seed_keywords = _keywords(cur, seed_uid)
            seed_authors = _authors(cur, seed_uid)

            # Semantic candidate pool (fetch vectors too, for MMR diversity).
            cur.execute(
                """
                SELECT pe.paper_uid, 1 - (pe.embedding <=> %s) AS sim, pe.embedding
                FROM paper_embeddings pe
                WHERE pe.paper_uid <> %s
                ORDER BY pe.embedding <=> %s
                LIMIT %s
                """,
                (seed_vec, seed_uid, seed_vec, CANDIDATE_POOL),
            )
            candidates = cur.fetchall()
            if not candidates:
                return []

            cand_uids = [c[0] for c in candidates]
            sim_by_uid = {c[0]: float(c[1]) for c in candidates}
            vec_by_uid = {c[0]: c[2] for c in candidates}
            meta = _hydrate(cur, cand_uids)
            kw_by_uid = _keywords_bulk(cur, cand_uids)
            auth_by_uid = _authors_bulk(cur, cand_uids)

    rec_by_uid: dict[str, Recommendation] = {}
    for uid in cand_uids:
        info = meta.get(uid)
        if not info:
            continue
        sim = sim_by_uid[uid]
        shared_kw = sorted(seed_keywords & kw_by_uid.get(uid, set()))
        shared_au = sorted(seed_authors & auth_by_uid.get(uid, set()))
        kw_score = len(shared_kw) / (len(seed_keywords) or 1)
        au_score = 1.0 if shared_au else 0.0
        rec_score = _recency(info.get("year"), seed_year)
        total = W_SEMANTIC * sim + W_KEYWORD * kw_score + W_AUTHOR * au_score + W_RECENCY * rec_score
        rec_by_uid[uid] = Recommendation(
            paper_id=str(info.get("paper_id") or uid),
            title=str(info.get("title") or ""),
            year=info.get("year"),
            field=str(info.get("field") or "unknown"),
            score=round(total, 6),
            semantic_similarity=round(sim, 6),
            shared_keywords=shared_kw[:10],
            shared_authors=shared_au[:5],
            factors={
                "semantic": round(W_SEMANTIC * sim, 6),
                "keyword_overlap": round(W_KEYWORD * kw_score, 6),
                "author_overlap": round(W_AUTHOR * au_score, 6),
                "recency": round(W_RECENCY * rec_score, 6),
            },
        )

    # MMR selection: balance relevance with diversity so the list isn't a cluster
    # of near-identical papers. Re-ranks the scored pool, not just top-by-score.
    ordered_uids = _mmr_select(
        {uid: rec_by_uid[uid].score for uid in rec_by_uid},
        {uid: vec_by_uid[uid] for uid in rec_by_uid},
        limit,
    )
    return [rec_by_uid[uid] for uid in ordered_uids]


def _mmr_select(score_by_uid: dict[str, float], vec_by_uid: dict, limit: int, lam: float = MMR_LAMBDA) -> list[str]:
    import numpy as np

    uids = list(score_by_uid)
    if not uids:
        return []
    vecs = {u: np.asarray(vec_by_uid[u], dtype=float) for u in uids}
    norms = {u: (float(np.linalg.norm(v)) or 1e-9) for u, v in vecs.items()}

    def cos(a: str, b: str) -> float:
        return float(np.dot(vecs[a], vecs[b]) / (norms[a] * norms[b]))

    selected: list[str] = []
    remaining = sorted(uids, key=lambda u: score_by_uid[u], reverse=True)
    while remaining and len(selected) < limit:
        if not selected:
            best = remaining[0]
        else:
            best = max(
                remaining,
                key=lambda u: lam * score_by_uid[u] - (1 - lam) * max(cos(u, s) for s in selected),
            )
        selected.append(best)
        remaining.remove(best)
    return selected


def _recency(year: int | None, seed_year: int | None) -> float:
    if not year or not seed_year:
        return 0.0
    gap = abs(seed_year - year)
    return max(0.0, 1.0 - gap / 10.0)


def _keywords(cur, paper_uid: str) -> set[str]:
    cur.execute(
        """
        SELECT k.normalized_keyword FROM paper_keywords pk
        JOIN keywords k ON k.keyword_uid = pk.keyword_uid
        WHERE pk.paper_uid = %s
        """,
        (paper_uid,),
    )
    return {row[0] for row in cur.fetchall()}


def _authors(cur, paper_uid: str) -> set[str]:
    cur.execute(
        """
        SELECT a.normalized_name FROM paper_authors pa
        JOIN authors a ON a.author_uid = pa.author_uid
        WHERE pa.paper_uid = %s
        """,
        (paper_uid,),
    )
    return {row[0] for row in cur.fetchall()}


def _keywords_bulk(cur, paper_uids: list[str]) -> dict[str, set[str]]:
    cur.execute(
        """
        SELECT pk.paper_uid, k.normalized_keyword FROM paper_keywords pk
        JOIN keywords k ON k.keyword_uid = pk.keyword_uid
        WHERE pk.paper_uid = ANY(%s)
        """,
        (paper_uids,),
    )
    out: dict[str, set[str]] = {}
    for paper_uid, kw in cur.fetchall():
        out.setdefault(paper_uid, set()).add(kw)
    return out


def _authors_bulk(cur, paper_uids: list[str]) -> dict[str, set[str]]:
    cur.execute(
        """
        SELECT pa.paper_uid, a.normalized_name FROM paper_authors pa
        JOIN authors a ON a.author_uid = pa.author_uid
        WHERE pa.paper_uid = ANY(%s)
        """,
        (paper_uids,),
    )
    out: dict[str, set[str]] = {}
    for paper_uid, name in cur.fetchall():
        out.setdefault(paper_uid, set()).add(name)
    return out


def _hydrate(cur, paper_uids: list[str]) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT paper_uid, coalesce(metadata->>'paper_id', source_id) AS paper_id, title, year, field
        FROM papers WHERE paper_uid = ANY(%s)
        """,
        (paper_uids,),
    )
    return {
        row[0]: {"paper_id": row[1], "title": row[2], "year": row[3], "field": row[4]}
        for row in cur.fetchall()
    }
