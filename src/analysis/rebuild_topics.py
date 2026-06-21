"""Rebuild only the topic-model assets with a configurable topic count.

The full analysis pipeline caps topics at 8 (16 total across LDA+NMF), which is
too coarse for a 160k-paper, 7-field corpus. This regenerates just the four
topic CSVs at a finer granularity, without re-running the whole pipeline.

Usage:
    python -m src.analysis.rebuild_topics --papers data/analysis/papers_clean.json \
        --output-dir data/analysis --max-topics 40
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analysis.assets import _build_topic_assets, _write_csv


def run(papers_path: Path, output_dir: Path, max_topics: int) -> dict[str, int]:
    papers = json.loads(Path(papers_path).read_text(encoding="utf-8"))
    comparison, keywords, paper_topics, year_share = _build_topic_assets(papers, max_topics=max_topics)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "topic_model_comparison.csv", comparison, ["model", "topics", "documents", "vocabulary", "quality_proxy"])
    _write_csv(output_dir / "topic_keywords.csv", keywords, ["model", "topic_id", "ranked_keywords"])
    _write_csv(output_dir / "paper_topics.csv", paper_topics, ["paper_id", "source", "year", "model", "topic_id", "topic_weight"])
    _write_csv(output_dir / "topic_year_share.csv", year_share, ["model", "topic_id", "year", "paper_count"])
    return {
        "topics_per_model": comparison[0]["topics"] if comparison else 0,
        "topic_keyword_rows": len(keywords),
        "paper_topic_rows": len(paper_topics),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild topic-model assets at finer granularity")
    parser.add_argument("--papers", type=Path, default=Path("data/analysis/papers_clean.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analysis"))
    parser.add_argument("--max-topics", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps(run(args.papers, args.output_dir, args.max_topics), ensure_ascii=False))


if __name__ == "__main__":
    main()
