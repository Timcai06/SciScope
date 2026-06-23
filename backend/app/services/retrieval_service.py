"""Hybrid retrieval over the PostgreSQL + pgvector service layer.

Combines lexical retrieval (PostgreSQL FTS on ``paper_chunks.search_document``)
with semantic retrieval (pgvector cosine over ``chunk_embeddings``) and fuses
the two ranked lists with Reciprocal Rank Fusion (RRF), deduplicated to the
paper level. Heavy dependencies (psycopg, pgvector, sentence-transformers) are
imported lazily so importing this module stays cheap and test-safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from backend.app.core.config import get_settings

RRF_K = 60
CHUNK_POOL = 40  # candidates pulled from each retrieval arm before fusion


@dataclass
class RetrievedPaper:
    paper_id: str
    title: str
    year: int | None
    authors: list[str]
    field: str
    snippet: str
    score: float
    matched_by: list[str]


def is_available() -> bool:
    """Hybrid retrieval is usable only when a DSN is configured and reachable."""
    settings = get_settings()
    if not settings.db_dsn:
        return False
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM papers LIMIT 1")
                return cur.fetchone() is not None
    except Exception:
        return False


def _connect():
    import psycopg

    return psycopg.connect(get_settings().db_dsn)


@lru_cache(maxsize=1)
def _has_embeddings() -> bool:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM chunk_embeddings LIMIT 1")
            return cur.fetchone() is not None
    except Exception:
        return False


def _filter_clause(field: str | None, year: int | None, params: list[Any]) -> str:
    clauses = ""
    if field:
        clauses += " AND p.field = %s"
        params.append(field)
    if year:
        clauses += " AND p.year = %s"
        params.append(year)
    return clauses


_TS_STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "is",
            "are", "with", "by", "as", "what", "how", "which"}


def _or_tsquery(query: str) -> str:
    """Build an OR tsquery so multi-term queries don't require ALL terms.

    websearch_to_tsquery ANDs terms, which fails when a query lists several words
    (a paper rarely contains every one). OR + ts_rank keeps recall while still
    ranking papers that match more/stronger terms higher.
    """
    terms = [t for t in _re.findall(r"[\w]+", query.lower(), _re.UNICODE) if len(t) > 1 and t not in _TS_STOP]
    # de-dup preserving order, cap to keep the query small
    seen: set[str] = set()
    uniq = [t for t in terms if not (t in seen or seen.add(t))][:12]
    return " | ".join(uniq)


def _fts_query(conn, tsquery_sql: str, query_text: str, field: str | None, year: int | None) -> list[tuple[str, str]]:
    params: list[Any] = [query_text]
    filters = _filter_clause(field, year, params)
    params.append(CHUNK_POOL)
    sql = f"""
        SELECT pc.paper_uid, pc.text
        FROM paper_chunks pc
        JOIN papers p ON p.paper_uid = pc.paper_uid
        , {tsquery_sql}('simple', %s) q
        WHERE pc.search_document @@ q{filters}
        ORDER BY ts_rank(pc.search_document, q) DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [(row[0], row[1]) for row in cur.fetchall()]


def _lexical_candidates(conn, query: str, field: str | None, year: int | None) -> list[tuple[str, str]]:
    # Precision-first: AND/phrase matches (websearch) lead so an exact title
    # query keeps its paper at rank 1; then OR matches fill in for recall on
    # multi-term queries (which AND alone would miss).
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for uid, text in _fts_query(conn, "websearch_to_tsquery", query, field, year):
        if uid not in seen:
            seen.add(uid)
            out.append((uid, text))
    tsq = _or_tsquery(query)
    if tsq:
        for uid, text in _fts_query(conn, "to_tsquery", tsq, field, year):
            if uid not in seen:
                seen.add(uid)
                out.append((uid, text))
    return out[:CHUNK_POOL]


def _semantic_candidates(conn, query: str, field: str | None, year: int | None) -> list[tuple[str, str]]:
    if not _has_embeddings():
        return []
    from pgvector.psycopg import register_vector

    from src.models.embeddings import get_embedder

    register_vector(conn)
    settings = get_settings()
    qvec = get_embedder(settings.embedding_model).encode_query(query)
    filter_params: list[Any] = []
    filters = _filter_clause(field, year, filter_params)
    sql = f"""
        SELECT pc.paper_uid, pc.text
        FROM chunk_embeddings ce
        JOIN paper_chunks pc ON pc.chunk_uid = ce.chunk_uid
        JOIN papers p ON p.paper_uid = pc.paper_uid
        WHERE ce.embedding_model = %s{filters}
        ORDER BY ce.embedding <=> %s
        LIMIT %s
    """
    exec_params = [settings.embedding_model, *filter_params, qvec, CHUNK_POOL]
    with conn.cursor() as cur:
        cur.execute(sql, exec_params)
        return [(row[0], row[1]) for row in cur.fetchall()]


def _rrf_fuse(*ranked_lists: list[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    arm_names = ["lexical", "semantic"]
    for arm_index, ranked in enumerate(ranked_lists):
        seen: set[str] = set()
        for rank, (paper_uid, snippet) in enumerate(ranked):
            if paper_uid in seen:
                continue  # only first (best) chunk per paper from each arm
            seen.add(paper_uid)
            entry = fused.setdefault(
                paper_uid, {"score": 0.0, "snippet": snippet, "matched_by": []}
            )
            entry["score"] += 1.0 / (RRF_K + rank + 1)
            entry["matched_by"].append(arm_names[arm_index] if arm_index < len(arm_names) else f"arm{arm_index}")
            if not entry["snippet"]:
                entry["snippet"] = snippet
    return fused


def _hydrate(conn, paper_uids: list[str]) -> dict[str, dict[str, Any]]:
    if not paper_uids:
        return {}
    meta: dict[str, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT paper_uid,
                   coalesce(metadata->>'paper_id', source_id) AS paper_id,
                   title, year, field
            FROM papers WHERE paper_uid = ANY(%s)
            """,
            (paper_uids,),
        )
        for paper_uid, paper_id, title, year, field in cur.fetchall():
            meta[paper_uid] = {
                "paper_id": paper_id,
                "title": title,
                "year": year,
                "field": field,
                "authors": [],
            }
        cur.execute(
            """
            SELECT pa.paper_uid, a.name
            FROM paper_authors pa
            JOIN authors a ON a.author_uid = pa.author_uid
            WHERE pa.paper_uid = ANY(%s)
            ORDER BY pa.paper_uid, pa.author_position
            """,
            (paper_uids,),
        )
        for paper_uid, name in cur.fetchall():
            if paper_uid in meta and len(meta[paper_uid]["authors"]) < 12:
                meta[paper_uid]["authors"].append(name)
    return meta


import re as _re

# Conversational/instruction filler stripped before retrieval so the topical
# core drives matching (e.g. "给我一篇最新的计算机视觉论文" -> "计算机视觉").
# Chinese fillers (substring-removed) and English fillers (word-boundary-removed,
# so 'recommend' does NOT mangle 'recommender'/'recommendation').
_FILLER_CN = [
    "请帮我", "帮我", "给我", "我想知道", "我想看看", "我想看", "告诉我", "麻烦",
    "推荐一下", "推荐", "介绍一下", "介绍", "列举", "列出", "找一下", "查一下",
    "最新的", "最新", "最近的", "最近", "一篇", "几篇", "一些", "一下", "若干",
    "有哪些", "是什么", "怎么样", "的研究", "的论文", "的文献",
    "论文", "文献", "请问", "请",
]
_FILLER_EN = [
    "recommend a paper on", "recommend a paper about", "a paper on", "papers on",
    "paper about", "papers about", "tell me about", "give me", "show me", "find me",
    "what are", "recommend", "please", "latest", "recent", "list",
]


def _clean_query(query: str) -> str:
    cleaned = query
    for f in _FILLER_CN:
        cleaned = cleaned.replace(f, " ")
    for f in _FILLER_EN:
        cleaned = _re.sub(rf"\b{_re.escape(f)}\b", " ", cleaned, flags=_re.IGNORECASE)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    # If stripping removed almost everything, keep the original query.
    return cleaned if len(cleaned) >= 2 else query


_RECENCY = ("最新", "最近", "近期", "今年", "newest", "latest", "recent", "most recent")


def search(query: str, limit: int = 10, field: str | None = None, year: int | None = None) -> list[RetrievedPaper]:
    query = (query or "").strip()
    if not query or not get_settings().db_dsn:
        return []
    from src.models.bilingual import expand_bilingual

    # Detect recency intent before filler stripping removes '最新'/'latest'.
    recency = any(r in query.lower() for r in _RECENCY)
    raw_query = query  # kept for the cross-encoder, which handles natural queries
    # Map known Chinese terms to English BEFORE stripping filler, so topical
    # terms like '推荐系统' aren't broken by the filler word '推荐'.
    query = expand_bilingual(query)
    query = _clean_query(query)
    with _connect() as conn:
        lexical = _lexical_candidates(conn, query, field, year)
        semantic = _semantic_candidates(conn, query, field, year)
        fused = _rrf_fuse(lexical, semantic)
        if not fused:
            return []
        ranked = sorted(fused.items(), key=lambda kv: kv[1]["score"], reverse=True)
        from src.models import reranker

        use_rerank = reranker.is_available()
        if use_rerank or recency:
            # Take a larger pool, hydrate, then cross-encoder rerank by relevance.
            pool = ranked[: max(limit * 3, 25)]
            meta = _hydrate(conn, [uid for uid, _ in pool])
            if use_rerank:
                pool = reranker.rerank(
                    raw_query,
                    pool,
                    text_of=lambda kv: f"{meta.get(kv[0], {}).get('title', '')} {kv[1].get('snippet', '')}"[:512],
                )
            if recency:
                # Among the most relevant, prefer the most recent papers.
                head = pool[: max(limit * 2, 10)]
                head.sort(key=lambda kv: (meta.get(kv[0], {}).get("year") or 0), reverse=True)
                pool = head + pool[max(limit * 2, 10):]
            top = pool[:limit]
        else:
            top = ranked[:limit]
            meta = _hydrate(conn, [paper_uid for paper_uid, _ in top])

    results: list[RetrievedPaper] = []
    for paper_uid, info in top:
        m = meta.get(paper_uid, {})
        results.append(
            RetrievedPaper(
                paper_id=str(m.get("paper_id") or paper_uid),
                title=str(m.get("title") or ""),
                year=m.get("year"),
                authors=m.get("authors") or [],
                field=str(m.get("field") or "unknown"),
                snippet=str(info.get("snippet") or "")[:400],
                score=round(float(info["score"]), 6),
                matched_by=info["matched_by"],
            )
        )
    return results
