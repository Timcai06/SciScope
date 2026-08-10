"""Contracts for the auditable bilingual silver route (E02 alternative)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation.stance import silver, silver_eval


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    raw = tmp_path / "raw"
    raw.mkdir()
    corpus = [{"doc_id": 10, "title": "T", "abstract": ["Official evidence."], "structured": False}]
    claims = [{"id": 1, "claim": "Official claim.", "evidence": {"10": [{"label": "SUPPORT", "sentences": [0]}]}, "cited_doc_ids": [10]}]
    _write_jsonl(raw / "corpus.jsonl", corpus)
    _write_jsonl(raw / "claims_dev.jsonl", claims)
    expected = {name: _hash(raw / name) for name in ("corpus.jsonl", "claims_dev.jsonl")}
    source = {"dataset": "SciFact", "split": "dev", "claim_id": 1, "doc_id": 10, "sentence_index": 0, "source_claim": "Official claim.", "source_evidence_sentence": "Official evidence.", "source_label": "SUPPORT"}
    rows = [
        {"id": "zh", "pair_id": "p", "language": "zh", "claim": "中文论断。", "evidence": "中文证据。", "evidence_sentence": "中文证据。", "label": "SUPPORT", "source": source, "derivation": {"kind": "translation", "translator": "project_manual_unreviewed"}, "review_status": "unreviewed_silver"},
        {"id": "cross", "pair_id": "p", "language": "cross", "claim": "中文论断。", "evidence": "Official evidence.", "evidence_sentence": "Official evidence.", "label": "SUPPORT", "source": source, "derivation": {"kind": "translation", "translator": "project_manual_unreviewed"}, "review_status": "unreviewed_silver"},
    ]
    silver_path = tmp_path / "silver.jsonl"
    _write_jsonl(silver_path, rows)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"schema_version": "sciscope-stance-silver-v1", "status": "frozen_silver_not_gold", "usage": "regression_and_model_agreement_only", "record_count": 2, "content_sha256": _hash(silver_path)}, ensure_ascii=False), encoding="utf-8")
    return raw, silver_path, manifest_path, expected


def test_frozen_silver_validates_source_and_explicitly_has_no_quality_claim(tmp_path: Path) -> None:
    raw, silver_path, manifest_path, expected = _fixture(tmp_path)
    report = silver.validate_frozen_set(manifest_path, silver_path, raw, expected_sha=expected)
    assert report["status"] == "data_ok_not_gold"
    assert report["quality_claim"] == "none"
    assert report["language_distribution"] == {"zh": 1, "cross": 1}


def test_frozen_silver_fails_closed_on_source_drift(tmp_path: Path) -> None:
    raw, silver_path, manifest_path, expected = _fixture(tmp_path)
    rows = silver.read_jsonl(silver_path)
    rows[0]["source"]["source_evidence_sentence"] = "forged"
    _write_jsonl(silver_path, rows)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["content_sha256"] = _hash(silver_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(silver.SilverDataError, match="source evidence sentence"):
        silver.validate_frozen_set(manifest_path, silver_path, raw, expected_sha=expected)


def test_agreement_is_hashed_and_not_a_quality_score(tmp_path: Path) -> None:
    raw, silver_path, manifest_path, expected = _fixture(tmp_path)
    left, right = tmp_path / "left.jsonl", tmp_path / "right.jsonl"
    _write_jsonl(left, [{"id": "zh", "stance": "SUPPORT"}, {"id": "cross", "stance": "CONTRADICT"}])
    _write_jsonl(right, [{"id": "zh", "stance": "SUPPORT"}, {"id": "cross", "stance": "SUPPORT"}])
    report = silver_eval.agreement_run(manifest_path, silver_path, raw, left, right, expected_sha=expected)
    assert report["stance_agreement"] == 0.5
    assert report["mode"] == "independent_model_agreement_not_quality_score"
    assert "accuracy" not in report


def test_agreement_rejects_prediction_id_drift(tmp_path: Path) -> None:
    raw, silver_path, manifest_path, expected = _fixture(tmp_path)
    left, right = tmp_path / "left.jsonl", tmp_path / "right.jsonl"
    _write_jsonl(left, [{"id": "zh", "stance": "SUPPORT"}, {"id": "cross", "stance": "SUPPORT"}])
    _write_jsonl(right, [{"id": "zh", "stance": "SUPPORT"}, {"id": "unexpected", "stance": "SUPPORT"}])
    with pytest.raises(silver.SilverDataError, match="id set mismatch"):
        silver_eval.agreement_run(manifest_path, silver_path, raw, left, right, expected_sha=expected)
