"""Validate a frozen bilingual silver set or measure model-to-model agreement.

Agreement is deliberately not scored against the silver labels.  It tells us
only whether two independently supplied prediction artefacts agree on a frozen
input; it is not accuracy, expert agreement, or a competition result.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.stance.silver import LABELS, SilverDataError, read_jsonl, sha256, validate_frozen_set

DEFAULT_SET = Path("evaluation/stance/bilingual_silver_v0.jsonl")
DEFAULT_MANIFEST = Path("evaluation/stance/bilingual_silver_v0.manifest.json")
DEFAULT_RAW_DIR = Path("data/scifact/raw")


def _prediction_index(path: Path, expected_ids: set[str]) -> dict[str, str]:
    rows = read_jsonl(path)
    indexed: dict[str, str] = {}
    for row in rows:
        item_id, stance = str(row.get("id") or ""), str(row.get("stance") or "").upper()
        if not item_id or item_id in indexed or stance not in LABELS:
            raise SilverDataError(f"invalid prediction row in {path}")
        indexed[item_id] = stance
    if set(indexed) != expected_ids:
        missing, unexpected = sorted(expected_ids - set(indexed)), sorted(set(indexed) - expected_ids)
        raise SilverDataError(f"prediction id set mismatch for {path}: missing={missing[:3]} unexpected={unexpected[:3]}")
    return indexed


def agreement_run(
    manifest_path: Path,
    silver_path: Path,
    raw_dir: Path,
    predictions_a: Path,
    predictions_b: Path,
    *,
    expected_sha: dict[str, str] | None = None,
) -> dict[str, Any]:
    admission = validate_frozen_set(manifest_path, silver_path, raw_dir, expected_sha=expected_sha)
    rows = read_jsonl(silver_path)
    expected_ids = {str(row["id"]) for row in rows}
    left, right = _prediction_index(predictions_a, expected_ids), _prediction_index(predictions_b, expected_ids)
    same = sum(left[item_id] == right[item_id] for item_id in expected_ids)
    language = {
        code: {
            "samples": len(group),
            "stance_agreement": round(sum(left[str(row["id"])] == right[str(row["id"])] for row in group) / len(group), 6),
        }
        for code in ("zh", "cross")
        if (group := [row for row in rows if row["language"] == code])
    }
    return {
        "mode": "independent_model_agreement_not_quality_score",
        "status": "agreement_computed_not_gold",
        "silver_input_sha256": sha256(silver_path),
        "predictions": {"a": {"path": str(predictions_a), "sha256": sha256(predictions_a)}, "b": {"path": str(predictions_b), "sha256": sha256(predictions_b)}},
        "samples": len(rows),
        "stance_agreement": round(same / len(rows), 6),
        "agreement_by_language": language,
        "prediction_label_distribution": {"a": dict(Counter(left.values())), "b": dict(Counter(right.values()))},
        "prohibited_interpretation": "Not accuracy, not expert agreement, not bilingual Gold v1, and not competition evidence.",
        "admission": admission,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SciScope bilingual silver admission / agreement (not scoring)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--silver-set", type=Path, default=DEFAULT_SET)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--predictions-a", type=Path)
    parser.add_argument("--predictions-b", type=Path)
    parser.add_argument("--allow-agreement", action="store_true", help="explicitly permit a non-quality agreement report")
    args = parser.parse_args()
    if bool(args.predictions_a) != bool(args.predictions_b):
        parser.error("--predictions-a and --predictions-b must be supplied together")
    if args.predictions_a and not args.allow_agreement:
        parser.error("--allow-agreement is required; agreement is not a quality score")
    try:
        report = agreement_run(args.manifest, args.silver_set, args.raw_dir, args.predictions_a, args.predictions_b) if args.predictions_a else validate_frozen_set(args.manifest, args.silver_set, args.raw_dir)
    except SilverDataError as exc:
        parser.exit(1, f"FAIL-CLOSED: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
