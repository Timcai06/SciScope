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
        archive_dir=args.archive_dir if args.archive_old else None,
        delete_archive=args.delete_archive,
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
    raw_canonical.add_argument("--archive-old", action="store_true")
    raw_canonical.add_argument("--archive-dir", type=Path, default=Path("data/raw_archive"))
    raw_canonical.add_argument("--delete-archive", action="store_true")
    raw_canonical.set_defaults(func=_raw_canonical)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
