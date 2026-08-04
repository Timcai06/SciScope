"""Blind double-annotation and adjudication contracts for ``gold_v1``."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Any

LABELS = {"SUPPORT", "CONTRADICT", "NEUTRAL"}
REQUIRED_CANDIDATE_FIELDS = {"id", "claim", "evidence", "language", "source"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number}: expected object")
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def validate_candidates(rows: list[dict[str, Any]], minimum: int = 80) -> None:
    ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        missing = REQUIRED_CANDIDATE_FIELDS - set(row)
        if missing:
            raise ValueError(f"candidate {index} missing: {', '.join(sorted(missing))}")
        item_id = str(row["id"]).strip()
        if not item_id or item_id in ids:
            raise ValueError(f"candidate {index} has missing or duplicate id")
        if any(str(row[key]).strip() == "" for key in ("claim", "evidence", "language", "source")):
            raise ValueError(f"candidate {item_id} has blank required content")
        if "label" in row or "stance" in row:
            raise ValueError(f"candidate {item_id} already has a label; packets must start blind")
        ids.add(item_id)
    if len(rows) < minimum:
        raise ValueError(f"need at least {minimum} candidates, got {len(rows)}")


def packet_rows(candidates: list[dict[str, Any]], seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Create independently ordered, label-free packets for two annotators."""
    base = [
        {
            "id": str(row["id"]),
            "claim": row["claim"],
            "evidence": row["evidence"],
            "language": row["language"],
            "source": row["source"],
            "stance": "",
            "evidence_sentence": "",
            "qualification": "",
            "notes": "",
        }
        for row in candidates
    ]
    first, second = list(base), list(base)
    random.Random(seed).shuffle(first)
    random.Random(seed + 1).shuffle(second)
    return first, second


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_annotation(row: dict[str, Any]) -> dict[str, Any]:
    stance = str(row.get("stance") or "").strip().upper()
    if stance not in LABELS:
        raise ValueError(f"{row.get('id')}: invalid stance {stance!r}")
    sentence = str(row.get("evidence_sentence") or "").strip()
    evidence = str(row.get("evidence") or "")
    if stance != "NEUTRAL" and (not sentence or sentence not in evidence):
        raise ValueError(f"{row.get('id')}: non-neutral stance requires a verbatim evidence_sentence")
    return {
        "id": str(row["id"]),
        "stance": stance,
        "evidence_sentence": sentence,
        "qualification": str(row.get("qualification") or "").strip(),
        "notes": str(row.get("notes") or "").strip(),
    }


def reconcile(candidates: list[dict[str, Any]], first: list[dict[str, Any]], second: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split exact label/sentence agreement from items requiring expert adjudication."""
    candidate_by_id = {str(row["id"]): row for row in candidates}
    if set(candidate_by_id) != {str(row.get("id")) for row in first} or set(candidate_by_id) != {str(row.get("id")) for row in second}:
        raise ValueError("candidate and annotator id sets must match exactly")
    agreed, queue = [], []
    for item_id, candidate in candidate_by_id.items():
        left, right = normalize_annotation(next(row for row in first if str(row["id"]) == item_id)), normalize_annotation(next(row for row in second if str(row["id"]) == item_id))
        same = (
            left["stance"] == right["stance"]
            and left["evidence_sentence"] == right["evidence_sentence"]
            and left["qualification"] == right["qualification"]
        )
        if same:
            agreed.append({**candidate, "label": left["stance"], "evidence_sentence": left["evidence_sentence"], "qualification": left["qualification"] or None, "annotation_status": "double_agreed"})
        else:
            queue.append({**candidate, "annotator_a": left, "annotator_b": right, "adjudicated_label": "", "adjudicated_sentence": "", "adjudicated_qualification": "", "adjudicator_notes": ""})
    return agreed, queue


def finalise_gold(agreed: list[dict[str, Any]], adjudications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate expert adjudications and produce the immutable evaluator format."""
    final = [dict(row) for row in agreed]
    for row in adjudications:
        adjudicated = {
            **row,
            "stance": row.get("adjudicated_label"),
            "evidence_sentence": row.get("adjudicated_sentence"),
            "qualification": row.get("adjudicated_qualification"),
        }
        label = normalize_annotation(adjudicated)
        final.append({
            "id": str(row["id"]), "claim": row["claim"], "evidence": row["evidence"],
            "language": row["language"], "source": row["source"], "label": label["stance"],
            "evidence_sentence": label["evidence_sentence"],
            "qualification": label["qualification"] or None, "annotation_status": "adjudicated",
        })
    return sorted(final, key=lambda row: str(row["id"]))
