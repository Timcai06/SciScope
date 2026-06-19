from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.harvest.normalize import normalize_raw_jsonl
from src.harvest.public_sources import SUPPORTED_SOURCES, default_raw_path, harvest_source


def _harvest(args: argparse.Namespace) -> None:
    output = args.output or default_raw_path(args.source, args.limit)
    count = harvest_source(source=args.source, output_path=output, limit=args.limit)
    print(json.dumps({"source": args.source, "output": str(output), "records": count}, ensure_ascii=False))


def _normalize(args: argparse.Namespace) -> None:
    stats = normalize_raw_jsonl(args.input, args.output)
    stats.update({"input": str(args.input), "output": str(args.output)})
    print(json.dumps(stats, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sciscope-harvest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    harvest = subparsers.add_parser("harvest", help="Harvest public paper metadata")
    harvest.add_argument("--source", default="openalex", choices=SUPPORTED_SOURCES)
    harvest.add_argument("--limit", type=int, default=500)
    harvest.add_argument("--output", type=Path)
    harvest.set_defaults(func=_harvest)

    normalize = subparsers.add_parser("normalize", help="Normalize raw JSONL into SciScope paper JSON")
    normalize.add_argument("--input", type=Path, default=Path("data/raw/openalex/works_sample.jsonl"))
    normalize.add_argument("--output", type=Path, default=Path("data/processed/papers.json"))
    normalize.set_defaults(func=_normalize)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
