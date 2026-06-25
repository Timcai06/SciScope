"""Generate chunk embeddings and upsert them into pgvector.

Streams ``data/processed/paper_chunks.jsonl``, encodes each chunk with the
local embedder, and upserts ``(chunk_uid, embedding_model, embedding)`` into the
``chunk_embeddings`` table. Supports resume (skips chunk_uids already embedded
with the same model) and chunk-type filtering to control cost.

维护级口径（不可变）：
* chunk 维度口径：每条 chunk 都以 `chunk_type` 为单位编码，默认覆盖
  ``title_abstract`` / ``full_text`` / ``keywords`` 三类。
* 续跑口径：resume 模式下只跳过当前 `embedding_model` 已存在的
  ``chunk_uid``；同一模型重复执行应可重入，不会引入重复行。
* 外键口径：仅为仍存在于 `paper_chunks`（并且类型匹配）的 chunk 建索引入库；
  主键缺失会导致 FK 失败，因此先聚合 `valid` 用于预过滤是必须约束。
* 持久化口径：`ON CONFLICT (chunk_uid)` 在数据库层做幂等重写，主键粒度是
  chunk_uid；`embedding_model` 可能被更新为新 run 的值。
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
    # 读取输入流时保持“过滤 -> yield”的单向通道，避免一次性加载所有 chunk。
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("chunk_type") in chunk_types:
                yield record


def _batched(items: Iterable[dict], size: int) -> Iterator[list[dict]]:
    # 将 JSONL 输入聚合为固定上限的批次；不是严格分页（尾批可小于 size），
    # 这是编码吞吐与内存占用之间的稳定折衷。
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
            # pending/skip 的不变量：
            # - pending：本批次有效 chunk，且该 model 未入库；
            # - skipped：已入库（resume 命中）或不在 valid 集合（已清理/失效）；
            # 这保证重跑统计可解释、可审计。
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
            # 提交颗粒度不影响最终写入逻辑，只影响故障恢复时“已落盘”窗口宽度。
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
