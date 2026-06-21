from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


RECENT_YEAR_START = 2022
RECENT_YEAR_END = 2026
RAG_FIELDS = (
    "doi",
    "title",
    "abstract",
    "authors",
    "year",
    "keywords",
    "field",
    "source",
    "source_id",
    "full_text",
)


def _load_papers(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _year_value(value: Any) -> int | None:
    if str(value or "").isdigit():
        return int(value)
    return None


def _has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return value is not None


def build_data_readiness_report(
    *,
    papers_path: str | Path = "data/analysis/papers_clean.json",
    output_path: str | Path = "output/assets/sciscope_data_report/data_layer_readiness.json",
    year_start: int = RECENT_YEAR_START,
    year_end: int = RECENT_YEAR_END,
    target_per_year: int = 10_000,
) -> dict[str, Any]:
    papers = _load_papers(Path(papers_path))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    years = [_year_value(paper.get("year")) for paper in papers]
    year_counts = Counter(year for year in years if year is not None)
    recent_years = list(range(year_start, year_end + 1))
    recent_counts = {str(year): year_counts.get(year, 0) for year in recent_years}
    year_deficits = {
        str(year): max(0, target_per_year - recent_counts[str(year)])
        for year in recent_years
    }
    deficit_years = [year for year, deficit in year_deficits.items() if deficit > 0]
    field_counts = Counter(str(paper.get("field_seed") or paper.get("field") or "unknown").lower() for paper in papers)
    source_counts = Counter(str(paper.get("source") or "unknown").lower() for paper in papers)

    full_text_records = sum(1 for paper in papers if _has_value(paper.get("full_text")))
    abstract_records = sum(1 for paper in papers if _has_value(paper.get("abstract")))
    rag_field_coverage = {
        field: {
            "count": sum(1 for paper in papers if _has_value(paper.get(field))),
            "rate": round(sum(1 for paper in papers if _has_value(paper.get(field))) / len(papers), 4) if papers else 0,
        }
        for field in RAG_FIELDS
    }
    report = {
        "records": len(papers),
        "recent_window": f"{year_start}-{year_end}",
        "recent_records": sum(recent_counts.values()),
        "target_per_year": target_per_year,
        "year_counts": recent_counts,
        "year_deficits_to_target": year_deficits,
        "year_balance_action": (
            "Year-balance target is met for the analysis window; prioritize source/field balance and text enrichment."
            if not deficit_years
            else (
                f"Backfill {', '.join(deficit_years)} by year-filtered source queries and avoid adding more "
                "over-represented years until the window approaches the target."
            )
        ),
        "source_counts": dict(source_counts.most_common()),
        "field_counts": dict(field_counts.most_common()),
        "text_coverage": {
            "abstract_records": abstract_records,
            "abstract_rate": round(abstract_records / len(papers), 4) if papers else 0,
            "full_text_records": full_text_records,
            "full_text_rate": round(full_text_records / len(papers), 4) if papers else 0,
            "full_text_gap_to_15000": max(0, 15_000 - full_text_records),
        },
        "rag_field_coverage": rag_field_coverage,
        "next_data_layer_tasks": [
            (
                "Maintain year-balance monitoring while prioritizing source and field balance."
                if not deficit_years
                else f"Backfill year-deficit partitions: {', '.join(deficit_years)}."
            ),
            "PMC/Unpaywall/CORE-oriented full-text enrichment and chunk generation.",
            "Schema enrichment for DOI, venue, URL, citation_count, institutions, author_ids, and text provenance.",
            "Deduplication upgrade using DOI first, then normalized title/year/source fallback.",
            "Generate chunk-level assets before RAG and agent development.",
        ],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
