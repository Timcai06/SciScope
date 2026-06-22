"""Generate chunk embeddings and upsert them into pgvector.

Streams ``data/processed/paper_chunks.jsonl``, encodes each chunk with the
local embedder, and upserts ``(chunk_uid, embedding_model, embedding)`` into the
``chunk_embeddings`` table. Supports resume (skips chunk_uids already embedded
with the same model) and chunk-type filtering to control cost.

Usage:
    python -m src.models.build_embeddings \
        --dsn postgresql://tim@localhost:5432/sciscope \
        --chunks data/processed/paper_chunks.jsonl \
        --chunk-types title_abstract full_text keywords \
        --batch-size 256
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable, Iterator

from src.models.embeddings import DEFAULT_MODEL, get_embedder

DEFAULT_DSN = os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")
DEFAULT_CHUNKS = Path("data/processed/paper_chunks.jsonl")
ALL_CHUNK_TYPES = ("title_abstract", "full_text", "keywords")


def iter_chunks(path: Path, chunk_types: set[str]) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("chunk_type") in chunk_types:
                yield record


def _batched(items: Iterable[dict], size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def build_embeddings(
    *,
    dsn: str = DEFAULT_DSN,
    chunks_path: Path = DEFAULT_CHUNKS,
    chunk_types: tuple[str, ...] = ALL_CHUNK_TYPES,
    batch_size: int = 256,
    model_name: str = DEFAULT_MODEL,
    resume: bool = True,
    commit_every: int = 10,
) -> dict[str, int]:
    import psycopg
    from pgvector.psycopg import register_vector

    embedder = get_embedder(model_name)
    selected = set(chunk_types)

    stats = {"embedded": 0, "skipped": 0, "total_seen": 0}

    with psycopg.connect(dsn) as conn:
        register_vector(conn)
        existing: set[str] = set()
        if resume:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chunk_uid FROM chunk_embeddings WHERE embedding_model = %s",
                    (model_name,),
                )
                existing = {row[0] for row in cur.fetchall()}

        # Only embed chunks that still exist in paper_chunks (dedup may have
        # removed some); embedding a missing chunk_uid violates the FK.
        with conn.cursor() as cur:
            cur.execute("SELECT chunk_uid FROM paper_chunks WHERE chunk_type = ANY(%s)", (list(selected),))
            valid: set[str] = {row[0] for row in cur.fetchall()}

        upsert_sql = """
            INSERT INTO chunk_embeddings (chunk_uid, embedding_model, embedding)
            VALUES (%s, %s, %s)
            ON CONFLICT (chunk_uid) DO UPDATE
            SET embedding = EXCLUDED.embedding, embedding_model = EXCLUDED.embedding_model
        """

        cur = conn.cursor()
        since_commit = 0
        for batch in _batched(iter_chunks(chunks_path, selected), batch_size):
            stats["total_seen"] += len(batch)
            pending = [c for c in batch if c["chunk_uid"] in valid and c["chunk_uid"] not in existing]
            stats["skipped"] += len(batch) - len(pending)
            if not pending:
                continue

            vectors = embedder.encode_passages([c.get("text") or "" for c in pending], batch_size)
            rows = [
                (chunk["chunk_uid"], model_name, vector)
                for chunk, vector in zip(pending, vectors)
            ]
            cur.executemany(upsert_sql, rows)
            stats["embedded"] += len(rows)
            since_commit += len(rows)
            # Commit every N batches (not every batch) to remove IO stalls.
            if since_commit >= batch_size * commit_every:
                conn.commit()
                since_commit = 0
                print(f"  embedded={stats['embedded']} skipped={stats['skipped']}", flush=True)
        conn.commit()
        cur.close()

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build chunk embeddings into pgvector")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--chunk-types", nargs="+", default=list(ALL_CHUNK_TYPES))
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--commit-every", type=int, default=10, help="commit every N batches")
    parser.add_argument("--no-resume", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    stats = build_embeddings(
        dsn=args.dsn,
        chunks_path=args.chunks,
        chunk_types=tuple(args.chunk_types),
        batch_size=args.batch_size,
        model_name=args.model,
        resume=not args.no_resume,
        commit_every=args.commit_every,
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
