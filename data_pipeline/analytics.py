from collections import Counter
from itertools import combinations
from typing import Any


def publication_trend(papers: list[dict[str, Any]]) -> list[dict[str, int]]:
    counts = Counter(paper.get("year") for paper in papers if paper.get("year") is not None)
    return [{"year": year, "count": counts[year]} for year in sorted(counts)]


def keyword_counts(papers: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for paper in papers:
        counts.update(paper.get("keywords") or [])
    return [{"keyword": keyword, "count": count} for keyword, count in counts.most_common(limit)]


def field_distribution(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(paper.get("field") or "unknown" for paper in papers)
    return [{"field": field, "count": counts[field]} for field in sorted(counts)]


def author_collaboration_edges(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    for paper in papers:
        authors = sorted(set(paper.get("authors") or []))
        counts.update(combinations(authors, 2))
    return [
        {"source": source, "target": target, "weight": weight}
        for (source, target), weight in sorted(counts.items())
    ]
