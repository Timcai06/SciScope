from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from src.infra.chunks import build_chunk_assets
from src.infra.postgres_loader import import_postgres


"""Command entrypoint for infra data operations.

Supported commands:
- chunks: emit paper_chunks.jsonl + summary
- schema: apply PostgreSQL schema SQL
- load-postgres: write papers/chunks into PostgreSQL

The module intentionally keeps CLI parsing close to side-effecting helpers for traceability.
"""


def _chunks(args: argparse.Namespace) -> None:
    # Build-only command: no DB side effects, just writes deterministic chunk assets.
    summary = build_chunk_assets(
        input_path=args.input,
        output_path=args.output,
        summary_path=args.summary,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
    )
    print(json.dumps(summary, ensure_ascii=False))


def _schema(args: argparse.Namespace) -> None:
    # Execute external psql against provided DSN and schema file.
    subprocess.run(["psql", args.dsn, "-f", str(args.file)], check=True)
    print(json.dumps({"dsn": args.dsn, "schema": str(args.file), "status": "applied"}, ensure_ascii=False))


def _load_postgres(args: argparse.Namespace) -> None:
    # Delegates loader defaults and batching to infra.postgres_loader.
    summary = import_postgres(
        dsn=args.dsn,
        papers_path=args.papers,
        chunks_path=args.chunks,
        batch_size=args.batch_size,
    )
    print(json.dumps(summary, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sciscope-infra")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chunks = subparsers.add_parser("chunks", help="Build chunk-level RAG assets from processed corpus")
    chunks.add_argument("--input", type=Path, default=Path("data/processed/papers_corpus.json"))
    chunks.add_argument("--output", type=Path, default=Path("data/processed/paper_chunks.jsonl"))
    chunks.add_argument("--summary", type=Path, default=Path("data/processed/paper_chunks.summary.json"))
    chunks.add_argument("--max-chars", type=int, default=1800)
    chunks.add_argument("--overlap-chars", type=int, default=180)
    chunks.set_defaults(func=_chunks)

    schema = subparsers.add_parser("schema", help="Apply PostgreSQL schema using psql")
    schema.add_argument("--dsn", default=os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope"))
    schema.add_argument("--file", type=Path, default=Path("infra/postgres/schema.sql"))
    schema.set_defaults(func=_schema)

    load = subparsers.add_parser("load-postgres", help="Load processed corpus and chunks into PostgreSQL")
    load.add_argument("--dsn", default=os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope"))
    load.add_argument("--papers", type=Path, default=Path("data/processed/papers_corpus.json"))
    load.add_argument("--chunks", type=Path, default=Path("data/processed/paper_chunks.jsonl"))
    load.add_argument("--batch-size", type=int, default=1000)
    load.set_defaults(func=_load_postgres)

    return parser


def main() -> None:
    # Keep argv contract explicit to avoid accidental invocation without a subcommand.
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
