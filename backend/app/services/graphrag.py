"""GraphRAG query expansion: let the knowledge graph participate in retrieval.

Pipeline: extract keyword entities from the question (match query tokens/bigrams
against the ``keywords`` table) -> expand along the co-occurrence graph (top
keywords that share papers with the seeds) -> return the neighbour terms so the
retriever can query-expand. This turns the knowledge graph from a display-only
artifact into an active part of the agent's reasoning.

Co-occurrence is computed live from ``paper_keywords`` with a hard cap on seed
papers so common keywords cannot explode the join.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.core.config import get_settings

_TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)
SEED_PAPER_CAP = 4000      # max seed papers scanned for co-occurrence
MAX_SEEDS = 6
MAX_NEIGHBOURS = 8


@dataclass
class GraphExpansion:
    entities: list[str] = field(default_factory=list)      # matched keyword entities
    neighbours: list[str] = field(default_factory=list)     # co-occurring graph neighbours


def _candidate_terms(question: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(question) if len(t) > 2]
    terms = set(tokens)
    for i in range(len(tokens) - 1):
        terms.add(f"{tokens[i]} {tokens[i + 1]}")
    for i in range(len(tokens) - 2):
        terms.add(f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}")
    return list(terms)


def _connect():
    import psycopg

    return psycopg.connect(get_settings().db_dsn)


def expand(question: str) -> GraphExpansion:
    """Return matched keyword entities and their co-occurrence-graph neighbours."""
    from src.models.keyword_filter import is_noise_keyword

    if not get_settings().db_dsn:
        return GraphExpansion()
    candidates = _candidate_terms(question)
    if not candidates:
        return GraphExpansion()
    try:
        with _connect() as conn, conn.cursor() as cur:
            # 1. entity extraction: which candidate terms are real corpus keywords
            cur.execute(
                """
                SELECT keyword_uid, keyword FROM keywords
                WHERE normalized_keyword = ANY(%s)
                LIMIT %s
                """,
                (candidates, MAX_SEEDS),
            )
            rows = cur.fetchall()
            if not rows:
                return GraphExpansion()
            seed_uids = [r[0] for r in rows]
            entities = [r[1] for r in rows]

            # 2. graph expansion: top co-occurring keywords (capped seed papers)
            cur.execute(
                """
                WITH seed_papers AS (
                    SELECT paper_uid FROM paper_keywords
                    WHERE keyword_uid = ANY(%(seeds)s)
                    LIMIT %(cap)s
                )
                SELECT k.keyword, count(*) AS c
                FROM paper_keywords pk
                JOIN seed_papers sp ON sp.paper_uid = pk.paper_uid
                JOIN keywords k ON k.keyword_uid = pk.keyword_uid
                WHERE pk.keyword_uid <> ALL(%(seeds)s)
                GROUP BY k.keyword
                ORDER BY c DESC
                LIMIT %(lim)s
                """,
                {"seeds": seed_uids, "cap": SEED_PAPER_CAP, "lim": MAX_NEIGHBOURS * 3},
            )
            neighbours = [
                kw for kw, _ in cur.fetchall()
                if not is_noise_keyword(kw) and kw.lower() not in {e.lower() for e in entities}
            ][:MAX_NEIGHBOURS]
    except Exception:
        return GraphExpansion()
    return GraphExpansion(entities=entities, neighbours=neighbours)


def expanded_query(question: str, expansion: GraphExpansion) -> str:
    """Append graph-neighbour keywords to the query for retrieval (query expansion)."""
    if not expansion.neighbours:
        return question
    return question + " " + " ".join(expansion.neighbours)
