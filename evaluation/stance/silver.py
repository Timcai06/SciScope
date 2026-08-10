"""Auditable, frozen bilingual *silver* stance-set contracts.

This module intentionally does not make a quality claim.  The Chinese and
cross-language rows link back to an official SciFact dev rationale, but their
translations and deterministic counterclaims are not expert annotations.  They
can therefore support reproducible regression and agreement checks only, never
replace a bilingual human Gold v1 evaluation.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.stance.scifact_data import RAW_SHA256, SciFactDataError, load_corpus, verify_split

LABELS = {"SUPPORT", "CONTRADICT", "NEUTRAL"}
LANGUAGES = {"zh", "cross"}
REQUIRED_ROW_FIELDS = {
    "id",
    "pair_id",
    "language",
    "claim",
    "evidence",
    "evidence_sentence",
    "label",
    "source",
    "derivation",
    "review_status",
}


class SilverDataError(RuntimeError):
    """Frozen silver set or its auditable SciFact source is invalid."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SilverDataError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise SilverDataError(f"{path}:{line_number}: expected object")
        rows.append(row)
    return rows


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SilverDataError(f"invalid manifest: {path}") from exc
    if not isinstance(manifest, dict):
        raise SilverDataError("manifest must be an object")
    return manifest


def validate_manifest(manifest: dict[str, Any], silver_path: Path) -> None:
    if manifest.get("schema_version") != "sciscope-stance-silver-v1":
        raise SilverDataError("unsupported silver manifest schema_version")
    if manifest.get("status") != "frozen_silver_not_gold":
        raise SilverDataError("silver manifest must be frozen_silver_not_gold")
    if manifest.get("usage") != "regression_and_model_agreement_only":
        raise SilverDataError("silver manifest must prohibit gold-quality scoring")
    expected = str(manifest.get("content_sha256") or "")
    if len(expected) != 64 or sha256(silver_path) != expected:
        raise SilverDataError("silver content SHA256 mismatch")
    if manifest.get("record_count") is not None and not isinstance(manifest["record_count"], int):
        raise SilverDataError("manifest record_count must be an integer")


def _read_claims(raw_dir: Path) -> dict[int, dict[str, Any]]:
    path = raw_dir / "claims_dev.jsonl"
    return {int(row["id"]): row for row in read_jsonl(path)}


def _source_has_rationale(source_claim: dict[str, Any], doc_id: int, sentence_index: int, label: str) -> bool:
    rationales = (source_claim.get("evidence") or {}).get(str(doc_id), [])
    return any(
        str(rationale.get("label") or "").upper() == label and sentence_index in rationale.get("sentences", [])
        for rationale in rationales
    )


def _validate_source(row: dict[str, Any], claims: dict[int, dict[str, Any]], corpus: dict[int, dict[str, Any]]) -> str:
    source = row["source"]
    if not isinstance(source, dict):
        raise SilverDataError(f"{row['id']}: source must be an object")
    required = {"dataset", "split", "claim_id", "doc_id", "sentence_index", "source_claim", "source_evidence_sentence", "source_label"}
    missing = required - set(source)
    if missing:
        raise SilverDataError(f"{row['id']}: source missing {sorted(missing)}")
    if source["dataset"] != "SciFact" or source["split"] != "dev":
        raise SilverDataError(f"{row['id']}: source must be SciFact dev")
    try:
        claim_id, doc_id, sentence_index = int(source["claim_id"]), int(source["doc_id"]), int(source["sentence_index"])
    except (TypeError, ValueError) as exc:
        raise SilverDataError(f"{row['id']}: source identifiers must be integers") from exc
    source_label = str(source["source_label"] or "").upper()
    claim = claims.get(claim_id)
    document = corpus.get(doc_id)
    if claim is None or document is None:
        raise SilverDataError(f"{row['id']}: unresolved SciFact claim or document")
    if source["source_claim"] != claim["claim"]:
        raise SilverDataError(f"{row['id']}: source_claim does not match SciFact")
    abstract = document["abstract"]
    if not 0 <= sentence_index < len(abstract) or source["source_evidence_sentence"] != abstract[sentence_index]:
        raise SilverDataError(f"{row['id']}: source evidence sentence does not match SciFact")
    if source_label not in {"SUPPORT", "CONTRADICT"} or not _source_has_rationale(claim, doc_id, sentence_index, source_label):
        raise SilverDataError(f"{row['id']}: source label/rationale is not an official SciFact dev rationale")
    return source_label


def _validate_derivation(row: dict[str, Any], source_label: str) -> None:
    derivation = row["derivation"]
    if not isinstance(derivation, dict):
        raise SilverDataError(f"{row['id']}: derivation must be an object")
    kind = derivation.get("kind")
    label = str(row["label"] or "").upper()
    if kind == "translation":
        if label != source_label:
            raise SilverDataError(f"{row['id']}: translation label must copy the official source label")
    elif kind == "counterclaim_from_source":
        if source_label not in {"SUPPORT", "CONTRADICT"} or label == source_label:
            raise SilverDataError(f"{row['id']}: counterclaim must invert a non-neutral source label")
        if derivation.get("rule") != "comparative_direction_reversal":
            raise SilverDataError(f"{row['id']}: unrecognised counterclaim rule")
    else:
        raise SilverDataError(f"{row['id']}: unsupported derivation kind")


def validate_rows(rows: list[dict[str, Any]], raw_dir: Path, *, expected_sha: dict[str, str] | None = None) -> dict[str, Any]:
    """Fail closed on frozen-set, provenance, or source-rationale drift.

    ``expected_sha`` exists solely for small synthetic test fixtures.  Production
    runs use the immutable official hashes in ``scifact_data.RAW_SHA256``.
    """
    try:
        verify_split(raw_dir, "dev", expected_sha or RAW_SHA256)
    except SciFactDataError as exc:
        raise SilverDataError(f"SciFact admission failed: {exc}") from exc
    claims, corpus = _read_claims(raw_dir), load_corpus(raw_dir / "corpus.jsonl")
    ids: set[str] = set()
    pairs: dict[str, set[str]] = {}
    for index, row in enumerate(rows, start=1):
        missing = REQUIRED_ROW_FIELDS - set(row)
        if missing:
            raise SilverDataError(f"row {index}: missing {sorted(missing)}")
        item_id, pair_id = str(row["id"]).strip(), str(row["pair_id"]).strip()
        if not item_id or item_id in ids or not pair_id:
            raise SilverDataError(f"row {index}: missing/duplicate id or blank pair_id")
        if row["language"] not in LANGUAGES:
            raise SilverDataError(f"{item_id}: language must be zh or cross")
        if str(row["label"] or "").upper() not in LABELS:
            raise SilverDataError(f"{item_id}: invalid silver label")
        if any(not str(row[field]).strip() for field in ("claim", "evidence", "evidence_sentence")):
            raise SilverDataError(f"{item_id}: claim/evidence/evidence_sentence must be nonblank")
        if str(row["evidence_sentence"]) not in str(row["evidence"]):
            raise SilverDataError(f"{item_id}: evidence_sentence must be verbatim in evidence")
        if row["review_status"] != "unreviewed_silver":
            raise SilverDataError(f"{item_id}: silver rows must state unreviewed_silver")
        source_label = _validate_source(row, claims, corpus)
        _validate_derivation(row, source_label)
        ids.add(item_id)
        pairs.setdefault(pair_id, set()).add(str(row["language"]))
    incomplete = sorted(pair_id for pair_id, languages in pairs.items() if languages != LANGUAGES)
    if incomplete:
        raise SilverDataError(f"bilingual pairs require zh and cross rows: {incomplete[:3]}")
    return {
        "records": len(rows),
        "pair_count": len(pairs),
        "language_distribution": dict(Counter(str(row["language"]) for row in rows)),
        "derived_label_distribution": dict(Counter(str(row["label"]).upper() for row in rows)),
        "review_status": "unreviewed_silver",
        "quality_claim": "none",
    }


def validate_frozen_set(manifest_path: Path, silver_path: Path, raw_dir: Path, *, expected_sha: dict[str, str] | None = None) -> dict[str, Any]:
    manifest = read_manifest(manifest_path)
    validate_manifest(manifest, silver_path)
    rows = read_jsonl(silver_path)
    if manifest.get("record_count") != len(rows):
        raise SilverDataError("manifest record_count does not match silver rows")
    report = validate_rows(rows, raw_dir, expected_sha=expected_sha)
    return {"mode": "silver-admission", "status": "data_ok_not_gold", "manifest": str(manifest_path), "silver_set": str(silver_path), **report}
