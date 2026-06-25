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


def _build_project_figures(args: argparse.Namespace) -> None:
    from src.analysis.project_figures import build_project_report_figures

    summary = build_project_report_figures(
        analysis_dir=args.analysis_dir,
        processed_dir=args.processed_dir,
        eval_dir=args.eval_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False))


def _build_corpus(args: argparse.Namespace) -> None:
    from src.analysis.corpus import build_processed_corpus

    summary = build_processed_corpus(
        input_path=args.input,
        output_path=args.output,
        summary_path=args.summary,
        year_start=args.year_start,
        year_end=args.year_end,
    )
    print(json.dumps(summary, ensure_ascii=False))


def _build_readiness(args: argparse.Namespace) -> None:
    from src.analysis.data_readiness import build_data_readiness_report

    summary = build_data_readiness_report(
        papers_path=args.papers,
        output_path=args.output,
        year_start=args.year_start,
        year_end=args.year_end,
        target_per_year=args.target_per_year,
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

    project_figures = subparsers.add_parser("project-figures", help="Build project-report product and system figures")
    project_figures.add_argument("--analysis-dir", type=Path, default=Path("data/analysis"))
    project_figures.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    project_figures.add_argument("--eval-dir", type=Path, default=Path("output/eval"))
    project_figures.add_argument("--output-dir", type=Path, default=Path("output/assets/sciscope_project_report"))
    project_figures.set_defaults(func=_build_project_figures)

    corpus = subparsers.add_parser("corpus", help="Build merged processed corpus from analysis papers")
    corpus.add_argument("--input", type=Path, default=Path("data/analysis/papers_clean.json"))
    corpus.add_argument("--output", type=Path, default=Path("data/processed/papers_corpus.json"))
    corpus.add_argument("--summary", type=Path, default=Path("data/processed/papers_corpus.summary.json"))
    corpus.add_argument("--year-start", type=int, default=2022)
    corpus.add_argument("--year-end", type=int, default=2026)
    corpus.set_defaults(func=_build_corpus)

    readiness = subparsers.add_parser("readiness", help="Audit corpus readiness for balanced data and RAG assets")
    readiness.add_argument("--papers", type=Path, default=Path("data/analysis/papers_clean.json"))
    readiness.add_argument("--output", type=Path, default=Path("output/assets/sciscope_data_report/data_layer_readiness.json"))
    readiness.add_argument("--year-start", type=int, default=2022)
    readiness.add_argument("--year-end", type=int, default=2026)
    readiness.add_argument("--target-per-year", type=int, default=10000)
    readiness.set_defaults(func=_build_readiness)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
