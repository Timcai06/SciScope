"""Contract tests for the offline, artefact-driven stance evaluator."""

from __future__ import annotations

from evaluation import eval_stance


def test_similarity_control_never_claims_contradiction() -> None:
    gold = eval_stance._read_jsonl(eval_stance.DEFAULT_GOLD)
    predictions = eval_stance.similarity_baseline(gold)
    assert {row["stance"] for row in predictions} <= {"SUPPORT", "NEUTRAL"}


def test_perfect_predictions_score_all_label_metrics() -> None:
    gold = eval_stance._read_jsonl(eval_stance.DEFAULT_GOLD)
    predictions = [
        {"id": row["id"], "stance": row["label"], "confidence": 1.0, "sentence": row["evidence_sentence"]}
        for row in gold
    ]
    metrics = eval_stance.evaluate(gold, predictions)
    assert metrics["macro_f1"] == 1.0
    assert metrics["evidence_sentence_exact_match"] == 1.0
    assert metrics["brier"] == 0.0


def test_missing_prediction_is_not_silently_dropped() -> None:
    gold = eval_stance._read_jsonl(eval_stance.DEFAULT_GOLD)
    try:
        eval_stance.evaluate(gold, [])
    except ValueError as exc:
        assert "missing predictions" in str(exc)
    else:
        raise AssertionError("missing predictions must fail the evaluation")
