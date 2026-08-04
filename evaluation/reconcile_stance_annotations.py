"""Reconcile two blinded stance packets and create an adjudication queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.stance.annotation import read_jsonl, reconcile, write_jsonl


def run(candidates: Path, annotator_a: Path, annotator_b: Path, out_dir: Path) -> dict:
    agreed, queue = reconcile(read_jsonl(candidates), read_jsonl(annotator_a), read_jsonl(annotator_b))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "agreed.jsonl", agreed)
    write_jsonl(out_dir / "adjudication_queue.jsonl", queue)
    report = {"agreed": len(agreed), "needs_adjudication": len(queue), "agreement_rate": round(len(agreed) / max(1, len(agreed) + len(queue)), 6)}
    (out_dir / "reconciliation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile SciScope double-annotation packets")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--annotator-a", type=Path, required=True)
    parser.add_argument("--annotator-b", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.candidates, args.annotator_a, args.annotator_b, args.out_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
