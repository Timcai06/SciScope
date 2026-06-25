"""Deduplicate the loaded PostgreSQL corpus using the same rules as the
processed-corpus builder (``src/analysis/corpus.py``).

Removes journal front-matter records and, within each dedupe-key group, keeps
the single most complete paper (full text > abstract length > #keywords >
#authors > most recent crawl). Deleting a paper cascades to its chunks,
embeddings, author/keyword links via the schema's ON DELETE CASCADE.

Usage:
    python -m src.infra.dedupe_db --dsn postgresql://tim@localhost:5432/sciscope [--apply]
Without --apply it only reports what would be removed (dry run).
"""

from __future__ import annotations

import argparse
import json
import os

from src.analysis.corpus import _dedupe_key, _is_front_matter, _normalize_title

DEFAULT_DSN = os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")


def _score(full_text_len: int, abstract_len: int, kw: int, authors: int, crawled_at: str) -> tuple:
    # Dedup scoring policy: prefer full-text enrichment, then abstract depth, then
    # keyword/author richness, then latest crawl date string for reproducibility.
    return (
        100 if full_text_len > 200 else 0,
        min(abstract_len // 100, 20),
        kw,
        min(authors, 10),
        crawled_at or "",
    )


def plan_deletions(dsn: str) -> tuple[list[str], dict[str, int]]:
    # Dedupe boundary: first classify journal/editorial front-matter and remove it directly,
    # then choose one winner per dedupe key, scheduling all losers.
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.paper_uid,
                   coalesce(p.metadata->>'paper_id', p.source_id) AS paper_id,
                   p.title, p.source, p.crawled_at,
                   length(p.abstract) AS abs_len, length(p.full_text) AS ft_len,
                   (SELECT count(*) FROM paper_keywords k WHERE k.paper_uid = p.paper_uid) AS kw,
                   (SELECT count(*) FROM paper_authors a WHERE a.paper_uid = p.paper_uid) AS au
            FROM papers p
            """
        )
        rows = cur.fetchall()

    to_delete: list[str] = []
    stats = {"total": len(rows), "front_matter": 0, "duplicates": 0}
    best_uid: dict[str, str] = {}
    best_score: dict[str, tuple] = {}

    for uid, paper_id, title, source, crawled_at, abs_len, ft_len, kw, au in rows:
        if _is_front_matter(_normalize_title(title)):
            stats["front_matter"] += 1
            to_delete.append(uid)
            continue
        key = _dedupe_key({"paper_id": paper_id, "title": title, "source": source})
        score = _score(ft_len or 0, abs_len or 0, kw or 0, au or 0, crawled_at or "")
        if key not in best_uid:
            best_uid[key] = uid
            best_score[key] = score
            continue
        stats["duplicates"] += 1
        # Keep the higher-scored record; delete the loser.
        if score > best_score[key]:
            to_delete.append(best_uid[key])
            best_uid[key] = uid
            best_score[key] = score
        else:
            to_delete.append(uid)

    return to_delete, stats


def run(dsn: str, apply: bool) -> dict:
    # Default mode is dry-run so operators can validate scope before destructive changes.
    import psycopg

    to_delete, stats = plan_deletions(dsn)
    stats["to_delete"] = len(to_delete)
    stats["kept"] = stats["total"] - len(to_delete)
    if apply and to_delete:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                for i in range(0, len(to_delete), 1000):
                    cur.execute("DELETE FROM papers WHERE paper_uid = ANY(%s)", (to_delete[i : i + 1000],))
            conn.commit()
        stats["applied"] = True
    else:
        stats["applied"] = False
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate the PostgreSQL corpus")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args()
    print(json.dumps(run(args.dsn, args.apply), ensure_ascii=False))


if __name__ == "__main__":
    main()
