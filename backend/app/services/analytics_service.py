from typing import Any

from data_pipeline.analytics import (
    author_collaboration_edges,
    field_distribution,
    keyword_counts,
    publication_trend,
)


def _year_range(papers: list[dict[str, Any]]) -> dict[str, int] | None:
    years = [paper["year"] for paper in papers if paper.get("year") is not None]
    if not years:
        return None
    return {"start": min(years), "end": max(years)}


def build_dashboard_overview(papers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_papers": len(papers),
        "year_range": _year_range(papers),
        "publication_trend": publication_trend(papers),
        "field_distribution": field_distribution(papers),
        "top_keywords": keyword_counts(papers, limit=10),
        "collaboration_edges": author_collaboration_edges(papers),
    }
