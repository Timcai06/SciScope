"""Offline evaluation of the recommendation model.

For a random sample of seed papers, fetch top-k recommendations and measure
relevance proxies (no manual labels): same-field rate, shared-keyword rate, and
mean semantic similarity. A good recommender should return papers in the same
field and sharing keywords far above the corpus base rate.
"""

from __future__ import annotations

import argparse
import json
import os
import random

from backend.app.services import recommend_service

DEFAULT_DSN = os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")


def run(dsn: str, sample: int, seed: int, limit: int) -> dict:
    import psycopg

    os.environ.setdefault("SCISCOPE_DB_DSN", dsn)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT coalesce(p.metadata->>'paper_id', p.source_id) AS paper_id, p.paper_uid, p.field
            FROM paper_embeddings pe JOIN papers p ON p.paper_uid = pe.paper_uid
            """
        )
        rows = cur.fetchall()
        seed_field = {r[1]: r[2] for r in rows}

    random.Random(seed).shuffle(rows)
    picked = rows[:sample]

    total_recs = same_field = shared_kw = 0
    sims = []
    seeds_with_recs = 0
    for paper_id, seed_uid, field in picked:
        recs = recommend_service.recommend(paper_id, limit=limit)
        if not recs:
            continue
        seeds_with_recs += 1
        for r in recs:
            total_recs += 1
            if r.field == field:
                same_field += 1
            if r.shared_keywords:
                shared_kw += 1
            sims.append(r.semantic_similarity)

    return {
        "seeds_sampled": len(picked),
        "seeds_with_recs": seeds_with_recs,
        "total_recommendations": total_recs,
        "same_field_rate": round(same_field / total_recs, 4) if total_recs else 0.0,
        "shared_keyword_rate": round(shared_kw / total_recs, 4) if total_recs else 0.0,
        "mean_semantic_similarity": round(sum(sims) / len(sims), 4) if sims else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline recommendation evaluation")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(run(args.dsn, args.sample, args.seed, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
