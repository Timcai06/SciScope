"""Analytics composition service for dashboard-style corpus summaries."""

from typing import Any

from data_pipeline.analytics import (
    author_collaboration_edges,
    field_distribution,
    keyword_counts,
    publication_trend,
)


def _year_range(papers: list[dict[str, Any]]) -> dict[str, int | None]:
    """Derive min/max year coverage from paper metadata."""
    years = [paper["year"] for paper in papers if paper.get("year") is not None]
    if not years:
        return {"start": None, "end": None}
    return {"start": min(years), "end": max(years)}


def build_dashboard_overview(papers: list[dict[str, Any]]) -> dict[str, Any]:
    """Compose dashboard aggregates used by overview endpoints/components.

    Contract: input is in-memory paper list, output is a stable dict containing
    counts, trend series, topic distribution, keywords and collaboration edges.
    """
    return {
        "total_papers": len(papers),
        "year_range": _year_range(papers),
        "publication_trend": publication_trend(papers),
        "field_distribution": field_distribution(papers),
        "top_keywords": keyword_counts(papers, limit=10),
        "collaboration_edges": author_collaboration_edges(papers),
    }
