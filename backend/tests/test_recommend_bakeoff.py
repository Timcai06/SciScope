from __future__ import annotations

import pytest

from evaluation.eval_recommend_bakeoff import _evaluate_one, _sample_manifest, render_markdown
from evaluation.recommend_bakeoff import EvalPaper, aggregate_baseline, cosine, percentile


def _paper(
    uid: str,
    *,
    field: str = "cs",
    keywords: tuple[str, ...] = (),
    embedding: tuple[float, ...] = (1.0, 0.0),
    popularity: float = 0.5,
) -> EvalPaper:
    return EvalPaper(uid, uid, field, frozenset(keywords), embedding, popularity)


def test_cosine_rejects_missing_or_mismatched_vectors() -> None:
    assert cosine((), ()) is None
    assert cosine((1.0,), (1.0, 2.0)) is None
    assert cosine((0.0, 0.0), (1.0, 0.0)) is None


def test_percentile_uses_nearest_rank_and_empty_is_none() -> None:
    assert percentile([], 0.95) is None
    assert percentile([1, 2, 3, 4], 0.5) == 2
    assert percentile([1, 2, 3, 4], 0.95) == 4
    with pytest.raises(ValueError):
        percentile([1], 1.1)


def test_aggregate_has_explicit_denominators_and_proxy_metrics() -> None:
    seed = _paper("seed", keywords=("rag",), popularity=0.8)
    rec_a = _paper("a", keywords=("rag",), popularity=0.25)
    rec_b = _paper("b", field="medicine", embedding=(0.0, 1.0), popularity=0.75)
    result = aggregate_baseline(
        name="dense",
        seeds=[seed],
        recommendations={"seed": [rec_a, rec_b]},
        latency_ms=[10.0],
        failures=[],
    )
    assert result["seeds_sampled"] == 1
    assert result["seeds_with_recommendations"] == 1
    assert result["total_recommendations"] == 2
    assert result["same_field_rate"] == 0.5
    assert result["shared_keyword_rate"] == 0.5
    assert result["mean_metadata_novelty_proxy"] == 0.5
    assert result["latency_ms"] == {"p50": 10.0, "p95": 10.0, "samples": 1}


def test_empty_results_are_not_silent_success() -> None:
    seed = _paper("seed")
    result = aggregate_baseline(
        name="keyword_tfidf",
        seeds=[seed],
        recommendations={"seed": []},
        latency_ms=[2.0],
        failures=[{"paper_id": "seed", "reason": "no_recommendations"}],
    )
    assert result["coverage"] == 0.0
    assert result["same_field_rate"] is None
    assert result["mean_intra_list_diversity"] is None
    assert result["failure_count"] == 1


def test_markdown_keeps_human_value_boundary_visible() -> None:
    report = {
        "results": [
            aggregate_baseline(
                name="popularity_proxy",
                seeds=[],
                recommendations={},
                latency_ms=[],
                failures=[],
            )
        ]
    }
    rendered = render_markdown(report)
    assert "user/expert value remains BLOCKED" in rendered
    assert "declares no winning recommender" in rendered
    assert "metadata richness" in rendered


def test_evaluator_failure_does_not_serialize_exception_message(monkeypatch) -> None:
    seed = _paper("seed")

    def fail(_seed):
        raise RuntimeError("postgresql://user:secret@private-host/db")

    monkeypatch.setattr(
        "evaluation.eval_recommend_bakeoff._hydrate",
        lambda *_args, **_kwargs: {},
    )
    result = _evaluate_one(
        object(),
        name="dense",
        seeds=[seed],
        ranker=fail,
        max_popularity=1.0,
    )
    assert result["failure_examples"] == [{"paper_id": "seed", "reason": "RuntimeError"}]
    assert "secret" not in str(result)


def test_sample_manifest_freezes_exact_seeds_and_candidate_fingerprint() -> None:
    first = _sample_manifest(["a", "b", "c", "d"], sample=2, seed=42)
    second = _sample_manifest(["a", "b", "c", "d"], sample=2, seed=42)
    changed = _sample_manifest(["a", "b", "c", "e"], sample=2, seed=42)
    assert first == second
    assert first["seed_uids"] == ["c", "b"]
    assert len(first["candidate_uid_sha256"]) == 64
    assert changed["candidate_uid_sha256"] != first["candidate_uid_sha256"]
