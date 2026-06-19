from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from src.harvest.normalize import paper_wrapper_to_paper


DEFAULT_SOURCES = ("openalex", "arxiv", "pubmed", "pmc", "crossref", "doaj")


def _iter_wrappers(
    raw_dir: Path,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    filename_template: str | None = None,
):
    for source in sources:
        source_dir = raw_dir / source
        if not source_dir.exists():
            continue
        paths = [source_dir / filename_template.format(source=source)] if filename_template else sorted(source_dir.glob("*.jsonl"))
        for path in paths:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield json.loads(line)


def _dedupe_key(paper: dict[str, Any], wrapper: dict[str, Any]) -> str:
    paper_id = str(paper.get("paper_id") or "").strip()
    source = str(wrapper.get("source") or "").strip()
    if paper_id:
        return f"{source}:{paper_id}"
    return f"{paper.get('title') or ''}::{paper.get('year') or ''}".lower()


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _paper_with_source(wrapper: dict[str, Any]) -> dict[str, Any]:
    paper = paper_wrapper_to_paper(wrapper)
    return {
        **paper,
        "source": str(wrapper.get("source") or ""),
        "source_id": str(wrapper.get("source_id") or ""),
        "query": str(wrapper.get("query") or ""),
        "field_seed": str(wrapper.get("field_seed") or ""),
        "crawled_at": str(wrapper.get("crawled_at") or ""),
    }


def build_analysis_assets(
    *,
    raw_dir: str | Path = "data/raw",
    output_dir: str | Path = "data/analysis",
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    filename_template: str | None = None,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    papers: list[dict[str, Any]] = []
    seen: set[str] = set()
    input_records = 0
    duplicates = 0

    for wrapper in _iter_wrappers(raw_path, sources=sources, filename_template=filename_template):
        input_records += 1
        paper = _paper_with_source(wrapper)
        key = _dedupe_key(paper, wrapper)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        papers.append(paper)

    paper_authors: list[dict[str, Any]] = []
    paper_keywords: list[dict[str, Any]] = []
    keyword_year_counts: Counter[tuple[str, int | str]] = Counter()
    edge_counts: Counter[tuple[str, str]] = Counter()

    for paper in papers:
        paper_id = str(paper.get("paper_id") or "")
        source = str(paper.get("source") or "")
        year = paper.get("year") or ""
        authors = [str(author).strip() for author in paper.get("authors") or [] if str(author).strip()]
        keywords = [str(keyword).strip() for keyword in paper.get("keywords") or [] if str(keyword).strip()]

        for index, author in enumerate(authors, start=1):
            paper_authors.append(
                {
                    "paper_id": paper_id,
                    "source": source,
                    "year": year,
                    "author": author,
                    "author_position": index,
                }
            )

        for keyword in keywords:
            row = {"paper_id": paper_id, "source": source, "year": year, "keyword": keyword}
            paper_keywords.append(row)
            if year:
                keyword_year_counts[(keyword, year)] += 1

        for author_a, author_b in combinations(sorted(set(authors)), 2):
            edge_counts[(author_a, author_b)] += 1

    keyword_year_rows = [
        {"keyword": keyword, "year": year, "count": count}
        for (keyword, year), count in sorted(keyword_year_counts.items(), key=lambda item: (str(item[0][0]), item[0][1]))
    ]
    edge_rows = [
        {"author_a": author_a, "author_b": author_b, "weight": weight}
        for (author_a, author_b), weight in sorted(edge_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    quality_by_source: dict[str, dict[str, int | str]] = defaultdict(
        lambda: {
            "source": "",
            "records": 0,
            "title_count": 0,
            "abstract_count": 0,
            "authors_count": 0,
            "year_count": 0,
            "keywords_count": 0,
            "full_text_count": 0,
        }
    )
    for paper in papers:
        source = str(paper.get("source") or "unknown")
        row = quality_by_source[source]
        row["source"] = source
        row["records"] = int(row["records"]) + 1
        row["title_count"] = int(row["title_count"]) + int(bool(paper.get("title")))
        row["abstract_count"] = int(row["abstract_count"]) + int(bool(paper.get("abstract")))
        row["authors_count"] = int(row["authors_count"]) + int(bool(paper.get("authors")))
        row["year_count"] = int(row["year_count"]) + int(bool(paper.get("year")))
        row["keywords_count"] = int(row["keywords_count"]) + int(bool(paper.get("keywords")))
        row["full_text_count"] = int(row["full_text_count"]) + int(bool(paper.get("full_text")))

    quality_rows = [quality_by_source[source] for source in sorted(quality_by_source)]

    output_path.joinpath("papers_clean.json").write_text(
        json.dumps(papers, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        output_path / "paper_authors.csv",
        paper_authors,
        ["paper_id", "source", "year", "author", "author_position"],
    )
    _write_csv(
        output_path / "paper_keywords.csv",
        paper_keywords,
        ["paper_id", "source", "year", "keyword"],
    )
    _write_csv(output_path / "keyword_year_matrix.csv", keyword_year_rows, ["keyword", "year", "count"])
    _write_csv(output_path / "author_collaboration_edges.csv", edge_rows, ["author_a", "author_b", "weight"])
    _write_csv(
        output_path / "source_quality_report.csv",
        quality_rows,
        [
            "source",
            "records",
            "title_count",
            "abstract_count",
            "authors_count",
            "year_count",
            "keywords_count",
            "full_text_count",
        ],
    )

    summary = {
        "input_records": input_records,
        "papers": len(papers),
        "duplicates": duplicates,
        "sources": sorted({paper.get("source") for paper in papers if paper.get("source")}),
        "paper_authors": len(paper_authors),
        "paper_keywords": len(paper_keywords),
        "keyword_year_rows": len(keyword_year_rows),
        "author_edges": len(edge_rows),
    }
    output_path.joinpath("summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
