from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.harvest.normalize import normalize_raw_jsonl
from src.harvest.public_sources import (
    SUPPORTED_SOURCES,
    YEAR_SUPPORTED_SOURCES,
    default_raw_path,
    harvest_source,
    harvest_source_year,
    year_raw_path,
)
from src.harvest.raw_governance import build_raw_canonical


def _harvest(args: argparse.Namespace) -> None:
    output = args.output or default_raw_path(args.source, args.limit)
    count = harvest_source(source=args.source, output_path=output, limit=args.limit)
    print(json.dumps({"source": args.source, "output": str(output), "records": count}, ensure_ascii=False))


def _harvest_year(args: argparse.Namespace) -> None:
    output = args.output or year_raw_path(args.source, args.year, args.limit)
    count = harvest_source_year(source=args.source, output_path=output, limit=args.limit, year=args.year)
    print(
        json.dumps(
            {"source": args.source, "year": args.year, "output": str(output), "records": count},
            ensure_ascii=False,
        )
    )


def _normalize(args: argparse.Namespace) -> None:
    stats = normalize_raw_jsonl(args.input, args.output)
    stats.update({"input": str(args.input), "output": str(args.output)})
    print(json.dumps(stats, ensure_ascii=False))


def _raw_canonical(args: argparse.Namespace) -> None:
    summary = build_raw_canonical(
        raw_dir=args.raw_dir,
        canonical_dir=args.canonical_dir,
        inventory_path=args.inventory,
        summary_path=args.summary,
        max_year=args.max_year,
        archive_dir=args.archive_dir if args.archive_old else None,
        delete_archive=args.delete_archive,
    )
    print(json.dumps(summary, ensure_ascii=False))


def _enrich_fulltext(args: argparse.Namespace) -> None:
    from src.harvest.fulltext_enrichment import enrich_fulltext_in_place

    years = [year.strip() for year in args.years.split(",") if year.strip()]
    summary = enrich_fulltext_in_place(
        canonical_dir=args.canonical_dir,
        source=args.source,
        years=years,
        limit=args.limit,
        sleep_seconds=args.sleep_seconds,
        text_limit=args.text_limit,
        timeout_seconds=args.timeout_seconds,
        max_download_bytes=args.max_download_bytes,
        max_attempts=args.max_attempts,
        checkpoint_every=args.checkpoint_every,
        browser_fallback=not args.no_browser_fallback,
        stable_only=args.stable_only,
    )
    print(json.dumps(summary, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sciscope-harvest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    harvest = subparsers.add_parser("harvest", help="Harvest public paper metadata")
    harvest.add_argument("--source", default="openalex", choices=SUPPORTED_SOURCES)
    harvest.add_argument("--limit", type=int, default=500)
    harvest.add_argument("--output", type=Path)
    harvest.set_defaults(func=_harvest)

    harvest_year = subparsers.add_parser("harvest-year", help="Harvest one source for a specific publication year")
    harvest_year.add_argument("--source", default="openalex", choices=YEAR_SUPPORTED_SOURCES)
    harvest_year.add_argument("--year", type=int, required=True)
    harvest_year.add_argument("--limit", type=int, default=500)
    harvest_year.add_argument("--output", type=Path)
    harvest_year.set_defaults(func=_harvest_year)

    normalize = subparsers.add_parser("normalize", help="Normalize raw JSONL into SciScope paper JSON")
    normalize.add_argument("--input", type=Path, default=Path("data/raw/openalex/works_sample.jsonl"))
    normalize.add_argument("--output", type=Path, default=Path("data/processed/papers.json"))
    normalize.set_defaults(func=_normalize)

    raw_canonical = subparsers.add_parser("raw-canonical", help="Build source/year canonical raw JSONL assets")
    raw_canonical.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    raw_canonical.add_argument("--canonical-dir", type=Path, default=Path("data/raw_canonical"))
    raw_canonical.add_argument("--inventory", type=Path, default=Path("data/raw_inventory.csv"))
    raw_canonical.add_argument("--summary", type=Path, default=Path("data/raw_canonical/summary.json"))
    raw_canonical.add_argument("--max-year", type=int)
    raw_canonical.add_argument("--archive-old", action="store_true")
    raw_canonical.add_argument("--archive-dir", type=Path, default=Path("data/raw_archive"))
    raw_canonical.add_argument("--delete-archive", action="store_true")
    raw_canonical.set_defaults(func=_raw_canonical)

    enrich_fulltext = subparsers.add_parser(
        "enrich-fulltext",
        help="Enrich existing canonical JSONL partitions in place without creating new raw files",
    )
    enrich_fulltext.add_argument("--canonical-dir", type=Path, default=Path("data/raw_canonical"))
    from src.harvest.fulltext_enrichment import SUPPORTED_SOURCES as FULLTEXT_ENRICH_SOURCES

    enrich_fulltext.add_argument("--source", default="arxiv", choices=FULLTEXT_ENRICH_SOURCES)
    enrich_fulltext.add_argument("--years", default="2022,2023,2024,2025,2026")
    enrich_fulltext.add_argument("--limit", type=int)
    enrich_fulltext.add_argument("--sleep-seconds", type=float, default=3.0)
    enrich_fulltext.add_argument("--text-limit", type=int, default=12_000)
    enrich_fulltext.add_argument("--timeout-seconds", type=int, default=20)
    enrich_fulltext.add_argument("--max-download-bytes", type=int, default=4_000_000)
    enrich_fulltext.add_argument("--max-attempts", type=int)
    enrich_fulltext.add_argument("--checkpoint-every", type=int, default=25)
    enrich_fulltext.add_argument("--no-browser-fallback", action="store_true")
    enrich_fulltext.add_argument("--stable-only", action="store_true")
    enrich_fulltext.set_defaults(func=_enrich_fulltext)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
