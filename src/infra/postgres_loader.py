from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from src.infra.chunks import paper_uid, stable_uid


DEFAULT_BATCH_SIZE = 1000


class PostgresDependencyError(RuntimeError):
    """Raised when psycopg is unavailable for PostgreSQL loading."""


def normalized_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def author_uid(name: str) -> str:
    return stable_uid("author", normalized_name(name))


def keyword_uid(keyword: str) -> str:
    return stable_uid("keyword", normalized_name(keyword))


def iter_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def batched(values: Iterable[tuple[Any, ...]], size: int = DEFAULT_BATCH_SIZE) -> Iterable[list[tuple[Any, ...]]]:
    batch: list[tuple[Any, ...]] = []
    for value in values:
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def import_postgres(
    *,
    dsn: str,
    papers_path: str | Path = "data/processed/papers_corpus_50k.json",
    chunks_path: str | Path = "data/processed/paper_chunks.jsonl",
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    try:
        import psycopg
    except ImportError as exc:
        raise PostgresDependencyError("Install psycopg first: python -m pip install 'psycopg[binary]'") from exc

    papers = json.loads(Path(papers_path).read_text(encoding="utf-8")) if Path(papers_path).exists() else []
    chunks = list(iter_jsonl(chunks_path))

    stats = {
        "papers": 0,
        "authors": 0,
        "paper_authors": 0,
        "keywords": 0,
        "paper_keywords": 0,
        "chunks": 0,
        "coauthor_edges": 0,
    }

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for batch in batched((_paper_row(paper) for paper in papers), batch_size):
                cur.executemany(PAPER_SQL, batch)
                stats["papers"] += len(batch)

            author_rows: dict[str, tuple[str, str, str]] = {}
            paper_author_rows: list[tuple[str, str, int]] = []
            keyword_rows: dict[str, tuple[str, str, str]] = {}
            paper_keyword_rows: list[tuple[str, str]] = []
            edge_weights: dict[tuple[str, str], dict[str, int | None]] = {}

            for paper in papers:
                p_uid = paper_uid(paper)
                year = paper.get("year") if isinstance(paper.get("year"), int) else None
                author_ids: list[str] = []
                for position, name in enumerate(paper.get("authors") or [], start=1):
                    norm = normalized_name(str(name))
                    if not norm:
                        continue
                    a_uid = author_uid(norm)
                    author_rows[a_uid] = (a_uid, str(name), norm)
                    paper_author_rows.append((p_uid, a_uid, position))
                    author_ids.append(a_uid)

                for keyword in paper.get("keywords") or []:
                    norm = normalized_name(str(keyword))
                    if not norm:
                        continue
                    k_uid = keyword_uid(norm)
                    keyword_rows[k_uid] = (k_uid, str(keyword), norm)
                    paper_keyword_rows.append((p_uid, k_uid))

                for author_a, author_b in combinations(sorted(set(author_ids)), 2):
                    key = (author_a, author_b)
                    edge = edge_weights.setdefault(key, {"weight": 0, "first_year": year, "last_year": year})
                    edge["weight"] = int(edge["weight"] or 0) + 1
                    if year is not None:
                        first_year = edge.get("first_year")
                        last_year = edge.get("last_year")
                        edge["first_year"] = year if first_year is None else min(int(first_year), year)
                        edge["last_year"] = year if last_year is None else max(int(last_year), year)

            for batch in batched(author_rows.values(), batch_size):
                cur.executemany(AUTHOR_SQL, batch)
                stats["authors"] += len(batch)
            for batch in batched(paper_author_rows, batch_size):
                cur.executemany(PAPER_AUTHOR_SQL, batch)
                stats["paper_authors"] += len(batch)
            for batch in batched(keyword_rows.values(), batch_size):
                cur.executemany(KEYWORD_SQL, batch)
                stats["keywords"] += len(batch)
            for batch in batched(paper_keyword_rows, batch_size):
                cur.executemany(PAPER_KEYWORD_SQL, batch)
                stats["paper_keywords"] += len(batch)

            edge_rows = [
                (author_a, author_b, int(edge["weight"] or 0), edge.get("first_year"), edge.get("last_year"))
                for (author_a, author_b), edge in edge_weights.items()
            ]
            for batch in batched(edge_rows, batch_size):
                cur.executemany(COAUTHOR_EDGE_SQL, batch)
                stats["coauthor_edges"] += len(batch)

            for batch in batched((_chunk_row(chunk) for chunk in chunks), batch_size):
                cur.executemany(CHUNK_SQL, batch)
                stats["chunks"] += len(batch)

        conn.commit()

    return stats


def _paper_row(paper: dict[str, Any]) -> tuple[Any, ...]:
    uid = paper_uid(paper)
    return (
        uid,
        str(paper.get("source") or ""),
        str(paper.get("source_id") or paper.get("paper_id") or uid),
        _doi_from_paper(paper),
        str(paper.get("title") or ""),
        str(paper.get("abstract") or ""),
        paper.get("year") if isinstance(paper.get("year"), int) else None,
        str(paper.get("field") or "unknown"),
        str(paper.get("full_text") or ""),
        str(paper.get("query") or ""),
        str(paper.get("field_seed") or ""),
        str(paper.get("crawled_at") or ""),
        bool(paper.get("is_recent_window")),
        json.dumps(
            {
                "paper_id": paper.get("paper_id") or "",
                "authors_count": len(paper.get("authors") or []),
                "keywords_count": len(paper.get("keywords") or []),
            },
            ensure_ascii=False,
        ),
    )


def _chunk_row(chunk: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(chunk.get("chunk_uid") or ""),
        str(chunk.get("paper_uid") or ""),
        int(chunk.get("chunk_index") or 0),
        str(chunk.get("chunk_type") or ""),
        str(chunk.get("source_field") or ""),
        str(chunk.get("text") or ""),
        int(chunk.get("token_estimate") or 0),
        json.dumps(chunk.get("metadata") or {}, ensure_ascii=False),
    )


def _doi_from_paper(paper: dict[str, Any]) -> str | None:
    source_id = str(paper.get("source_id") or paper.get("paper_id") or "").strip()
    if source_id.lower().startswith("10."):
        return source_id
    return None


PAPER_SQL = """
INSERT INTO papers (
    paper_uid, source, source_id, doi, title, abstract, year, field, full_text,
    query, field_seed, crawled_at, is_recent_window, metadata, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
ON CONFLICT (paper_uid) DO UPDATE SET
    source = EXCLUDED.source,
    source_id = EXCLUDED.source_id,
    doi = EXCLUDED.doi,
    title = EXCLUDED.title,
    abstract = EXCLUDED.abstract,
    year = EXCLUDED.year,
    field = EXCLUDED.field,
    full_text = EXCLUDED.full_text,
    query = EXCLUDED.query,
    field_seed = EXCLUDED.field_seed,
    crawled_at = EXCLUDED.crawled_at,
    is_recent_window = EXCLUDED.is_recent_window,
    metadata = EXCLUDED.metadata,
    updated_at = now()
"""

AUTHOR_SQL = """
INSERT INTO authors (author_uid, name, normalized_name)
VALUES (%s, %s, %s)
ON CONFLICT (author_uid) DO UPDATE SET name = EXCLUDED.name, normalized_name = EXCLUDED.normalized_name
"""

PAPER_AUTHOR_SQL = """
INSERT INTO paper_authors (paper_uid, author_uid, author_position)
VALUES (%s, %s, %s)
ON CONFLICT (paper_uid, author_uid) DO UPDATE SET author_position = EXCLUDED.author_position
"""

KEYWORD_SQL = """
INSERT INTO keywords (keyword_uid, keyword, normalized_keyword)
VALUES (%s, %s, %s)
ON CONFLICT (keyword_uid) DO UPDATE SET keyword = EXCLUDED.keyword, normalized_keyword = EXCLUDED.normalized_keyword
"""

PAPER_KEYWORD_SQL = """
INSERT INTO paper_keywords (paper_uid, keyword_uid)
VALUES (%s, %s)
ON CONFLICT (paper_uid, keyword_uid) DO NOTHING
"""

COAUTHOR_EDGE_SQL = """
INSERT INTO coauthor_edges (author_uid_a, author_uid_b, weight, first_year, last_year)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (author_uid_a, author_uid_b) DO UPDATE SET
    weight = EXCLUDED.weight,
    first_year = EXCLUDED.first_year,
    last_year = EXCLUDED.last_year
"""

CHUNK_SQL = """
INSERT INTO paper_chunks (
    chunk_uid, paper_uid, chunk_index, chunk_type, source_field, text, token_estimate, metadata
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
ON CONFLICT (chunk_uid) DO UPDATE SET
    paper_uid = EXCLUDED.paper_uid,
    chunk_index = EXCLUDED.chunk_index,
    chunk_type = EXCLUDED.chunk_type,
    source_field = EXCLUDED.source_field,
    text = EXCLUDED.text,
    token_estimate = EXCLUDED.token_estimate,
    metadata = EXCLUDED.metadata
"""
