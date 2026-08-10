"""Reproducible non-L3 SciFact cited-document baseline.

This is a supervised TF-IDF + logistic-regression control.  It trains only on
``claims_train.jsonl`` and predicts each *cited document* of the requested
split.  Candidate documents are supplied by SciFact's ``cited_doc_ids``;
therefore this is an oracle-candidate label/rationale baseline, **not** open
retrieval and **not** a SciScope L3 stance run.  It writes the exact official
document-evidence prediction schema consumed by :mod:`scifact_eval`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.stance.scifact_data import SciFactDataError, load_corpus, verify_split

DEFAULT_RAW_DIR = Path("data/scifact/raw")
MODEL_ID = "tfidf-1to2-logreg-c1-min_df2-random_state0"
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _claim_document_label(claim: dict[str, Any], doc_id: int) -> str:
    rationales = (claim.get("evidence") or {}).get(str(doc_id), [])
    labels = {str(rationale.get("label") or "").upper() for rationale in rationales}
    if "SUPPORT" in labels:
        return "SUPPORT"
    if "CONTRADICT" in labels:
        return "CONTRADICT"
    return "NEUTRAL"


def _document_text(claim: dict[str, Any], document: dict[str, Any]) -> str:
    return f"{claim['claim']} [SEP] {document['title']} {' '.join(document['abstract'])}"


def _sentence_overlap(claim: str, sentence: str) -> float:
    claim_terms = set(_TOKEN_RE.findall(claim.lower()))
    sentence_terms = set(_TOKEN_RE.findall(sentence.lower()))
    return len(claim_terms & sentence_terms) / max(1, len(claim_terms | sentence_terms))


def _top_sentences(claim: str, document: dict[str, Any]) -> list[int]:
    ranked = sorted(
        enumerate(document["abstract"]), key=lambda item: (-_sentence_overlap(claim, item[1]), item[0])
    )
    return [index for index, _sentence in ranked[:3]]


def _require_sklearn() -> tuple[Any, Any, Any]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
    except ImportError as exc:
        raise SciFactDataError(
            "scikit-learn is required for scifact_baseline; use the project Python with this dependency installed"
        ) from exc
    return TfidfVectorizer, LogisticRegression, make_pipeline


def generate_predictions(raw_dir: Path, split: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Train on official train only and produce official-format predictions."""
    if split == "test":
        raise SciFactDataError("test labels are unavailable; this Wave 0 baseline is intentionally dev-only")
    verify_split(raw_dir, "train")
    split_stats = verify_split(raw_dir, split)
    corpus = load_corpus(raw_dir / "corpus.jsonl")
    train_claims = _read_jsonl(raw_dir / "claims_train.jsonl")
    target_claims = _read_jsonl(raw_dir / f"claims_{split}.jsonl")
    train_texts: list[str] = []
    train_labels: list[str] = []
    for claim in train_claims:
        for doc_id in claim["cited_doc_ids"]:
            document = corpus[int(doc_id)]
            train_texts.append(_document_text(claim, document))
            train_labels.append(_claim_document_label(claim, int(doc_id)))

    TfidfVectorizer, LogisticRegression, make_pipeline = _require_sklearn()
    model = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        LogisticRegression(max_iter=1000, random_state=0),
    )
    model.fit(train_texts, train_labels)
    outputs: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    candidate_count = 0
    for claim in target_claims:
        doc_ids = [int(doc_id) for doc_id in claim["cited_doc_ids"]]
        labels = model.predict([_document_text(claim, corpus[doc_id]) for doc_id in doc_ids])
        evidence: dict[str, dict[str, Any]] = {}
        for doc_id, label in zip(doc_ids, labels):
            label = str(label)
            label_counts[label] += 1
            candidate_count += 1
            if label != "NEUTRAL":
                evidence[str(doc_id)] = {"label": label, "sentences": _top_sentences(claim["claim"], corpus[doc_id])}
        outputs.append({"id": int(claim["id"]), "evidence": evidence})
    report = {
        "model": MODEL_ID,
        "training_split": "train",
        "training_claims": len(train_claims),
        "training_cited_document_pairs": len(train_texts),
        "training_label_distribution": dict(Counter(train_labels)),
        "prediction_split": split,
        "prediction_claims": len(target_claims),
        "candidate_boundary": "SciFact cited_doc_ids only (oracle candidate documents; no open-corpus retrieval)",
        "candidate_document_pairs": candidate_count,
        "predicted_label_distribution_before_neutral_omission": dict(label_counts),
        "non_neutral_documents_written": sum(len(row["evidence"]) for row in outputs),
        "rationale_selector": "top 3 claim/abstract-sentence lexical Jaccard overlap",
        "prediction_schema": "SciFact document-evidence JSONL; NEUTRAL omitted as empty evidence",
        "data_stats": split_stats.as_dict(),
        "non_l3_notice": "A supervised baseline over SciFact oracle candidates; it is not open retrieval, an L3 stance run, or a SciScope capability claim.",
    }
    return outputs, report


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a non-L3 SciFact oracle-candidate baseline prediction JSONL")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--split", choices=["dev", "train", "test"], default="dev")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        predictions, report = generate_predictions(args.raw_dir, args.split)
    except SciFactDataError as exc:
        raise SystemExit(f"FAIL-CLOSED: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in predictions), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
