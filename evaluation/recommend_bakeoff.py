"""Pure metric helpers for the G04b recommendation bake-off.

The metrics in this module are automatic proxies.  They intentionally do not
turn field/keyword agreement into a user-quality claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class EvalPaper:
    """Minimal paper view required by the offline metrics."""

    paper_uid: str
    paper_id: str
    field: str
    keywords: frozenset[str]
    embedding: tuple[float, ...]
    popularity_proxy: float


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    """Return cosine similarity, or ``None`` for missing/malformed vectors."""

    if not left or len(left) != len(right):
        return None
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return None
    return dot / (left_norm * right_norm)


def percentile(values: Iterable[float], quantile: float) -> float | None:
    """Nearest-rank percentile with explicit empty-input semantics."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_baseline(
    *,
    name: str,
    seeds: list[EvalPaper],
    recommendations: dict[str, list[EvalPaper]],
    latency_ms: list[float],
    failures: list[dict[str, str]],
) -> dict:
    """Aggregate one baseline without inventing relevance or user labels."""

    total = 0
    same_field = 0
    shared_keyword = 0
    semantic: list[float] = []
    novelty: list[float] = []
    list_diversities: list[float] = []

    for seed in seeds:
        recs = recommendations.get(seed.paper_uid, [])
        pair_distances: list[float] = []
        for index, rec in enumerate(recs):
            total += 1
            same_field += int(bool(seed.field) and seed.field == rec.field)
            shared_keyword += int(bool(seed.keywords & rec.keywords))
            seed_similarity = cosine(seed.embedding, rec.embedding)
            if seed_similarity is not None:
                semantic.append(seed_similarity)
            novelty.append(1.0 - min(1.0, max(0.0, rec.popularity_proxy)))
            for other in recs[index + 1 :]:
                pair_similarity = cosine(rec.embedding, other.embedding)
                if pair_similarity is not None:
                    pair_distances.append(1.0 - pair_similarity)
        if pair_distances:
            list_diversities.append(sum(pair_distances) / len(pair_distances))

    seeds_with_recs = sum(bool(recommendations.get(seed.paper_uid)) for seed in seeds)
    evaluated = len(seeds)
    return {
        "baseline": name,
        "seeds_sampled": evaluated,
        "seeds_with_recommendations": seeds_with_recs,
        "coverage": round(seeds_with_recs / evaluated, 6) if evaluated else 0.0,
        "total_recommendations": total,
        "same_field_rate": round(same_field / total, 6) if total else None,
        "shared_keyword_rate": round(shared_keyword / total, 6) if total else None,
        "mean_seed_semantic_similarity": _round_optional(_mean(semantic)),
        "mean_intra_list_diversity": _round_optional(_mean(list_diversities)),
        "mean_metadata_novelty_proxy": _round_optional(_mean(novelty)),
        "latency_ms": {
            "p50": _round_optional(median(latency_ms) if latency_ms else None, 3),
            "p95": _round_optional(percentile(latency_ms, 0.95), 3),
            "samples": len(latency_ms),
        },
        "failure_count": len(failures),
        "failure_examples": failures[:10],
    }


def _round_optional(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None else None
