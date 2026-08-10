"""SciFact evaluation entrypoint with a fail-closed official-format scorer.

The default remains an admission-only dry run.  A score is emitted only when
both ``--predictions`` and ``--allow-score`` are supplied.  Prediction files
use SciFact's *document evidence* submission schema, not a flattened claim
label: one row per claim, with an ``evidence`` mapping of document id to a
``SUPPORT``/``CONTRADICT`` label and sentence indexes.  Empty evidence is the
only representation of a NEUTRAL prediction.

This scorer implements the public dev-set abstract and sentence F1 rules.  It
is deliberately not a leaderboard submission client: test labels are absent,
and a local dev score is not an L3 result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evaluation.stance.scifact_data import SciFactDataError, load_corpus, verify_split

DEFAULT_RAW_DIR = "data/scifact/raw"
PREDICTION_LABELS = {"SUPPORT", "CONTRADICT"}


def dry_run(raw_dir: Path, split: str, expected_sha: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate the official raw files without producing any benchmark score."""
    stats = verify_split(raw_dir, split, expected_sha)
    return {
        "mode": "dry-run",
        "status": "data_ok",
        "note": "数据完整性检查通过；未计算 benchmark 分数（无预测文件/评分授权）。",
        "stats": stats.as_dict(),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SciFactDataError(f"missing predictions file: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SciFactDataError(f"{path}:{number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise SciFactDataError(f"{path}:{number}: expected prediction object")
        rows.append(row)
    return rows


def _normalise_predictions(
    rows: list[dict[str, Any]], claims: list[dict[str, Any]], corpus: dict[int, dict[str, Any]], path: Path
) -> dict[int, dict[int, dict[str, Any]]]:
    """Validate the public SciFact prediction schema and key it by claim/doc.

    The validation intentionally rejects a flattened ``stance`` field.  Such a
    file cannot be evaluated by the official rationale-aware protocol because
    it does not identify an evidence document or a sentence set.
    """
    expected_ids = {int(row["id"]) for row in claims}
    seen: set[int] = set()
    output: dict[int, dict[int, dict[str, Any]]] = {}
    for number, row in enumerate(rows, start=1):
        try:
            claim_id = int(row["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SciFactDataError(f"{path}:{number}: prediction requires integer id") from exc
        if claim_id in seen:
            raise SciFactDataError(f"{path}:{number}: duplicate prediction id {claim_id}")
        seen.add(claim_id)
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            raise SciFactDataError(f"{path}:{number}: evidence must be an object (empty object means NEUTRAL)")
        documents: dict[int, dict[str, Any]] = {}
        for doc_key, item in evidence.items():
            try:
                doc_id = int(doc_key)
            except (TypeError, ValueError) as exc:
                raise SciFactDataError(f"{path}:{number}: non-integer evidence doc key {doc_key!r}") from exc
            if doc_id in documents:
                raise SciFactDataError(f"{path}:{number}: duplicate evidence doc id {doc_id}")
            if doc_id not in corpus:
                raise SciFactDataError(f"{path}:{number}: evidence doc {doc_id} missing from corpus")
            if not isinstance(item, dict):
                raise SciFactDataError(f"{path}:{number}: evidence for doc {doc_id} must be an object")
            label = str(item.get("label") or "").upper()
            if label not in PREDICTION_LABELS:
                raise SciFactDataError(f"{path}:{number}: doc {doc_id} label must be SUPPORT or CONTRADICT")
            sentences = item.get("sentences")
            if not isinstance(sentences, list) or not all(isinstance(sentence, int) for sentence in sentences):
                raise SciFactDataError(f"{path}:{number}: doc {doc_id} sentences must be an integer list")
            abstract_length = len(corpus[doc_id]["abstract"])
            if any(sentence < 0 or sentence >= abstract_length for sentence in sentences):
                raise SciFactDataError(f"{path}:{number}: doc {doc_id} sentence index out of bounds")
            documents[doc_id] = {"label": label, "sentences": sentences}
        output[claim_id] = documents

    missing = sorted(expected_ids - seen)
    extras = sorted(seen - expected_ids)
    if missing:
        raise SciFactDataError(f"missing predictions for {len(missing)} ids (e.g. {missing[:3]})")
    if extras:
        raise SciFactDataError(f"predictions include {len(extras)} unknown ids (e.g. {extras[:3]})")
    return output


def _f1(correct: int, predicted: int, gold: int) -> dict[str, float]:
    precision = correct / predicted if predicted else 0.0
    recall = correct / gold if gold else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(2 * precision * recall / (precision + recall), 6) if precision + recall else 0.0,
    }


def _gold_evidence(claim: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    return {int(doc_id): rationales for doc_id, rationales in (claim.get("evidence") or {}).items()}


def score_predictions(
    claims: list[dict[str, Any]], predictions: dict[int, dict[int, dict[str, Any]]]
) -> dict[str, Any]:
    """Score public-format predictions with SciFact's abstract/sentence rules."""
    abstract_correct = abstract_predicted = abstract_gold = 0
    sentence_correct = sentence_predicted = sentence_gold = 0
    for claim in claims:
        claim_id = int(claim["id"])
        gold_docs = _gold_evidence(claim)
        predicted_docs = predictions[claim_id]
        abstract_gold += len(gold_docs)
        for rationales in gold_docs.values():
            for rationale in rationales:
                sentence_gold += len(rationale["sentences"])

        for doc_id, predicted in predicted_docs.items():
            predicted_sentences = set(predicted["sentences"])
            abstract_sentences = set(predicted["sentences"][:3])  # official abstract score cap
            abstract_predicted += 1
            sentence_predicted += len(predicted_sentences)
            rationales = gold_docs.get(doc_id, [])
            label_matches = bool(rationales) and all(rationale["label"] == predicted["label"] for rationale in rationales)
            abstract_completed = any(
                set(rationale["sentences"]) <= abstract_sentences for rationale in rationales if label_matches
            )
            completed = [set(rationale["sentences"]) for rationale in rationales if label_matches and set(rationale["sentences"]) <= predicted_sentences]
            if abstract_completed:
                abstract_correct += 1
                sentence_correct += sum(len(rationale) for rationale in completed)

    return {
        "abstract": _f1(abstract_correct, abstract_predicted, abstract_gold),
        "sentence": _f1(sentence_correct, sentence_predicted, sentence_gold),
        "counts": {
            "claims": len(claims),
            "gold_abstracts": abstract_gold,
            "predicted_abstracts": abstract_predicted,
            "correct_abstracts": abstract_correct,
            "gold_sentences": sentence_gold,
            "predicted_sentences": sentence_predicted,
            "correct_sentences": sentence_correct,
        },
    }


def _failure_examples(
    claims: list[dict[str, Any]], predictions: dict[int, dict[int, dict[str, Any]]], limit: int = 3
) -> dict[str, list[dict[str, Any]]]:
    """Return bounded audit examples; these are diagnostics, never training input."""
    incorrect_predictions: list[dict[str, Any]] = []
    missed_gold_abstracts: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = int(claim["id"])
        gold_docs = _gold_evidence(claim)
        predicted_docs = predictions[claim_id]
        for doc_id, predicted in predicted_docs.items():
            rationales = gold_docs.get(doc_id, [])
            abstract_sentences = set(predicted["sentences"][:3])
            complete = bool(rationales) and all(
                rationale["label"] == predicted["label"] for rationale in rationales
            ) and any(set(rationale["sentences"]) <= abstract_sentences for rationale in rationales)
            if not complete and len(incorrect_predictions) < limit:
                incorrect_predictions.append(
                    {
                        "claim_id": claim_id,
                        "claim": claim["claim"],
                        "doc_id": doc_id,
                        "predicted": predicted,
                        "gold_rationales": rationales,
                    }
                )
        for doc_id, rationales in gold_docs.items():
            predicted = predicted_docs.get(doc_id)
            abstract_sentences = set(predicted["sentences"][:3]) if predicted else set()
            complete = bool(predicted) and all(
                rationale["label"] == predicted["label"] for rationale in rationales
            ) and any(set(rationale["sentences"]) <= abstract_sentences for rationale in rationales)
            if not complete and len(missed_gold_abstracts) < limit:
                missed_gold_abstracts.append(
                    {
                        "claim_id": claim_id,
                        "claim": claim["claim"],
                        "doc_id": doc_id,
                        "predicted": predicted,
                        "gold_rationales": rationales,
                    }
                )
    return {
        "incorrect_predicted_abstracts": incorrect_predictions,
        "missed_gold_abstracts": missed_gold_abstracts,
    }


def scored_run(raw_dir: Path, split: str, predictions_path: Path) -> dict[str, Any]:
    """Run fail-closed local dev scoring against admitted official data."""
    if split == "test":
        raise SciFactDataError("SciFact test labels are not public; local --allow-score only supports train/dev")
    stats = verify_split(raw_dir, split)
    corpus = load_corpus(raw_dir / "corpus.jsonl")
    claims = _read_jsonl(raw_dir / f"claims_{split}.jsonl")
    predictions = _normalise_predictions(_read_jsonl(predictions_path), claims, corpus, predictions_path)
    return {
        "mode": "scored",
        "status": "scored_local_dev",
        "split": split,
        "predictions": str(predictions_path),
        "prediction_schema": "SciFact document-evidence JSONL: id + evidence.{doc_id}.{label,sentences}",
        "data_stats": stats.as_dict(),
        "metrics": score_predictions(claims, predictions),
        "failure_examples": _failure_examples(claims, predictions),
        "note": "本地公开 dev/train 评分，不是官方 test leaderboard，也不构成 SciScope L3 通过。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SciFact 锚点数据准入与官方格式本地评分入口")
    parser.add_argument("--split", choices=["train", "dev", "test"], default="dev")
    parser.add_argument("--raw-dir", type=Path, default=Path(DEFAULT_RAW_DIR))
    parser.add_argument("--predictions", type=Path, help="SciFact document-evidence JSONL prediction file")
    parser.add_argument("--allow-score", action="store_true", help="显式授权输出本地公开 split 分数")
    parser.add_argument("--output", type=Path, help="optional JSON report output path")
    args = parser.parse_args()

    if args.predictions and not args.allow_score:
        print("拒绝：提供了 --predictions 但未提供 --allow-score；默认不做评分。", file=sys.stderr)
        sys.exit(2)
    if args.allow_score and not args.predictions:
        print("拒绝：--allow-score 需要 --predictions。", file=sys.stderr)
        sys.exit(2)
    try:
        report = scored_run(args.raw_dir, args.split, args.predictions) if args.predictions else dry_run(args.raw_dir, args.split)
    except SciFactDataError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        sys.exit(1)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
