"""Build the paper-level recommendation model.

Recommendation is served at query time from the service layer, but it needs a
paper-level embedding to find semantic neighbours. This script materialises
``paper_embeddings`` (mean of a paper's chunk embeddings) using pgvector's
``avg(vector)`` aggregate and builds an ivfflat index on it. The runtime
recommender (``backend/app/services/recommend_service.py``) then fuses semantic
similarity with keyword/author overlap and recency, with explanation factors.

Output (the deliverable "recommendation model files"):
    paper_embeddings table + index in PostgreSQL
    models/recommend/recommend_model.json (metadata)
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DSN = os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")
OUTPUT_DIR = Path("models/recommend")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS paper_embeddings (
    paper_uid TEXT PRIMARY KEY REFERENCES papers (paper_uid) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

POPULATE_SQL = """
INSERT INTO paper_embeddings (paper_uid, embedding_model, embedding, chunk_count)
SELECT pc.paper_uid, %s AS embedding_model, avg(ce.embedding) AS embedding, count(*) AS chunk_count
FROM chunk_embeddings ce
JOIN paper_chunks pc ON pc.chunk_uid = ce.chunk_uid
WHERE ce.embedding_model = %s
GROUP BY pc.paper_uid
ON CONFLICT (paper_uid) DO UPDATE
SET embedding = EXCLUDED.embedding,
    embedding_model = EXCLUDED.embedding_model,
    chunk_count = EXCLUDED.chunk_count;
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS paper_embeddings_vector_idx
    ON paper_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""


def run(dsn: str = DEFAULT_DSN, model_name: str = "intfloat/multilingual-e5-base") -> dict:
    import psycopg

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            cur.execute("TRUNCATE paper_embeddings")
            cur.execute(POPULATE_SQL, (model_name, model_name))
            cur.execute(INDEX_SQL)
            cur.execute("ANALYZE paper_embeddings")
            cur.execute("SELECT count(*) FROM paper_embeddings")
            count = cur.fetchone()[0]
        conn.commit()

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": model_name,
        "paper_embeddings": int(count),
        "signals": ["semantic_similarity", "keyword_overlap", "author_overlap", "recency"],
        "note": "Paper vectors are the mean of their chunk embeddings; recommendations are served live via pgvector.",
    }
    (OUTPUT_DIR / "recommend_model.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SciScope recommendation model (paper_embeddings)")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--model", default="intfloat/multilingual-e5-base")
    args = parser.parse_args()
    print(json.dumps(run(args.dsn, args.model), ensure_ascii=False))


if __name__ == "__main__":
    main()
