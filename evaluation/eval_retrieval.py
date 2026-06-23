"""Automatic retrieval-quality evaluation (no manual labels needed).

Uses a self-retrieval protocol: sample papers that have embeddings, derive a
query from each paper (its title, and separately its keywords), run the hybrid
retriever, and check at what rank the source paper comes back. Reports
recall@k, MRR, and mean latency so retrieval "效果与效率" can be shown
quantitatively.

Usage:
    python -m evaluation.eval_retrieval --dsn postgresql://tim@localhost:5432/sciscope --sample 200
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time

from backend.app.services import retrieval_service

DEFAULT_DSN = os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")
KS = (1, 5, 10)


def _sample_papers(dsn: str, sample: int, seed: int) -> list[dict]:
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # Only papers that have an embedding are retrievable by the semantic arm.
        cur.execute(
            """
            SELECT coalesce(p.metadata->>'paper_id', p.source_id) AS paper_id, p.title, p.paper_uid
            FROM paper_embeddings pe JOIN papers p ON p.paper_uid = pe.paper_uid
            WHERE length(p.title) > 15
            """
        )
        rows = cur.fetchall()
        keyword_map: dict[str, list[str]] = {}
        cur.execute(
            """
            SELECT pa.paper_uid, k.keyword
            FROM paper_keywords pa JOIN keywords k ON k.keyword_uid = pa.keyword_uid
            WHERE pa.paper_uid = ANY(%s)
            """,
            ([r[2] for r in rows],),
        )
        for paper_uid, kw in cur.fetchall():
            keyword_map.setdefault(paper_uid, []).append(kw)

    random.Random(seed).shuffle(rows)
    picked = rows[:sample]
    return [
        {"paper_id": pid, "title": title, "keywords": keyword_map.get(uid, [])}
        for pid, title, uid in picked
    ]


def _rank_of(results, target_id: str) -> int | None:
    for index, item in enumerate(results, start=1):
        if item.paper_id == target_id:
            return index
    return None


def _evaluate(papers: list[dict], query_fn, limit: int) -> dict:
    ranks: list[int | None] = []
    latencies: list[float] = []
    used = 0
    for paper in papers:
        query = query_fn(paper)
        if not query:
            continue
        used += 1
        start = time.time()
        results = retrieval_service.search(query, limit=limit)
        latencies.append(time.time() - start)
        ranks.append(_rank_of(results, paper["paper_id"]))

    hits = [r for r in ranks if r is not None]
    metrics = {"queries": used, "found_in_topk": len(hits)}
    for k in KS:
        metrics[f"recall@{k}"] = round(sum(1 for r in hits if r <= k) / used, 4) if used else 0.0
    metrics["mrr@10"] = round(sum(1.0 / r for r in hits) / used, 4) if used else 0.0
    metrics["mean_latency_ms"] = round(1000 * sum(latencies) / len(latencies), 1) if latencies else 0.0
    return metrics


def run(dsn: str, sample: int, seed: int, limit: int) -> dict:
    if not retrieval_service.is_available():
        raise RuntimeError("Hybrid retrieval unavailable; set SCISCOPE_DB_DSN and load the corpus.")
    papers = _sample_papers(dsn, sample, seed)
    report = {
        "sample_papers": len(papers),
        "limit": limit,
        "by_title": _evaluate(papers, lambda p: p["title"], limit),
        "by_keywords": _evaluate(papers, lambda p: ", ".join(p["keywords"][:6]) if p["keywords"] else "", limit),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-retrieval evaluation of hybrid search")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    os.environ.setdefault("SCISCOPE_DB_DSN", args.dsn)
    print(json.dumps(run(args.dsn, args.sample, args.seed, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
