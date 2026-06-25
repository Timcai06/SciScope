from collections import Counter
from itertools import combinations
from typing import Any, TypedDict


"""Analytics adapters over the normalized paper dicts.

These helpers deliberately operate on plain dicts so callers from scripts/tests do not
depend on a full object graph. Output keys are intentionally normalized/sorted
for stable downstream snapshots and regression checks.
"""


class TrendPoint(TypedDict):
    year: int
    count: int


class KeywordCount(TypedDict):
    keyword: str
    count: int


class FieldCount(TypedDict):
    field: str
    count: int


class CollaborationEdge(TypedDict):
    source: str
    target: str
    weight: int


def publication_trend(papers: list[dict[str, Any]]) -> list[TrendPoint]:
    # Year index only counts explicit integer years after normalization.
    counts = Counter(paper.get("year") for paper in papers if paper.get("year") is not None)
    return [{"year": year, "count": counts[year]} for year in sorted(counts)]


def keyword_counts(papers: list[dict[str, Any]], limit: int = 20) -> list[KeywordCount]:
    # Sort by descending frequency then keyword text for deterministic ties.
    counts: Counter[str] = Counter()
    for paper in papers:
        counts.update(paper.get("keywords") or [])
    return [
        {"keyword": keyword, "count": count}
        for keyword, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    ]


def field_distribution(papers: list[dict[str, Any]]) -> list[FieldCount]:
    # "unknown" is explicit fallback for missing fields at normalization time.
    counts = Counter(paper.get("field") or "unknown" for paper in papers)
    return [{"field": field, "count": counts[field]} for field in sorted(counts)]


def author_collaboration_edges(papers: list[dict[str, Any]]) -> list[CollaborationEdge]:
    # Deduplicate coauthor pairs per paper first; this avoids double-counting same pair.
    counts: Counter[tuple[str, str]] = Counter()
    for paper in papers:
        authors = sorted(set(paper.get("authors") or []))
        counts.update(combinations(authors, 2))
    return [
        {"source": source, "target": target, "weight": weight}
        for (source, target), weight in sorted(counts.items())
    ]
