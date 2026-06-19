from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analysis.assets import DEFAULT_SOURCES, build_analysis_assets

def _build_assets(args: argparse.Namespace) -> None:
    sources = tuple(args.sources.split(",")) if args.sources else DEFAULT_SOURCES
    summary = build_analysis_assets(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        sources=sources,
        filename_template=args.filename_template,
    )
    summary.update({"raw_dir": str(args.raw_dir), "output_dir": str(args.output_dir)})
    print(json.dumps(summary, ensure_ascii=False))


def _build_figures(args: argparse.Namespace) -> None:
    from src.analysis.figures import build_report_figures

    summary = build_report_figures(
        analysis_dir=args.analysis_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sciscope-analysis")
    subparsers = parser.add_subparsers(dest="command", required=True)

    assets = subparsers.add_parser("assets", help="Build analysis-ready data assets from raw source JSONL")
    assets.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    assets.add_argument("--output-dir", type=Path, default=Path("data/analysis"))
    assets.add_argument("--sources", help="Comma-separated source list")
    assets.add_argument("--filename-template", help="Per-source raw filename template, e.g. {source}_500.jsonl")
    assets.set_defaults(func=_build_assets)

    figures = subparsers.add_parser("figures", help="Build report-ready chart assets from analysis tables")
    figures.add_argument("--analysis-dir", type=Path, default=Path("data/analysis"))
    figures.add_argument("--output-dir", type=Path, default=Path("output/assets/sciscope_data_report"))
    figures.set_defaults(func=_build_figures)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
