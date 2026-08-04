"""Build two blinded stance-annotation packets from candidate claim-evidence rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.stance.annotation import packet_rows, read_jsonl, sha256, validate_candidates, write_jsonl


def run(candidates_path: Path, out_dir: Path, seed: int = 20260804, minimum: int = 80) -> dict:
    candidates = read_jsonl(candidates_path)
    validate_candidates(candidates, minimum=minimum)
    first, second = packet_rows(candidates, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    first_path, second_path = out_dir / "annotator_a.jsonl", out_dir / "annotator_b.jsonl"
    write_jsonl(first_path, first)
    write_jsonl(second_path, second)
    manifest = {
        "schema_version": "stance-gold-v1",
        "candidate_count": len(candidates),
        "seed": seed,
        "source": str(candidates_path),
        "packets": {"annotator_a": {"path": str(first_path), "sha256": sha256(first_path)}, "annotator_b": {"path": str(second_path), "sha256": sha256(second_path)}},
        "status": "awaiting_independent_annotation",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Create blinded SciScope stance annotation packets")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--minimum", type=int, default=80)
    args = parser.parse_args()
    print(json.dumps(run(args.candidates, args.out_dir, args.seed, args.minimum), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
