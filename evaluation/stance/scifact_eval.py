"""SciFact 锚点评测入口（E02a）—— 默认 dry-run / 数据完整性检查。

纪律（E02a 目标书）：
- 默认只做数据准入与完整性检查，**不输出任何 benchmark 分数**；
- 只有显式提供 ``--predictions <file>``（已批准的模型预测）且 ``--allow-score``
  同时存在时，才可能计算分数；两者缺一即拒绝。
- 本文件不训练模型、不伪造分数、不宣称 L3 已通过。

用法：
    python -m evaluation.stance.scifact_eval --split dev          # dry-run（默认）
    python -m evaluation.stance.scifact_eval --split dev --predictions preds.jsonl --allow-score
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evaluation.stance.scifact_data import SciFactDataError, verify_split

DEFAULT_RAW_DIR = "data/scifact/raw"


def dry_run(raw_dir: Path, split: str, expected_sha: dict[str, str] | None = None) -> dict:
    """数据准入 + 完整性检查；不产生分数。缺文件/哈希/schema 不符 → fail-closed。"""
    stats = verify_split(raw_dir, split, expected_sha)
    return {
        "mode": "dry-run",
        "status": "data_ok",
        "note": "数据完整性检查通过；未计算 benchmark 分数（无已批准预测/评分授权）。",
        "stats": stats.as_dict(),
    }


def scored_run(raw_dir: Path, split: str, predictions_path: Path) -> dict:
    """显式评分路径：需要 --predictions 与 --allow-score 同时满足。

    按 SciFact 官方 label 协议计算 claim 级准确率（证据缺失的 claim 视为
    NEUTRAL 基准）；此处仅为可执行入口框架——预测文件 schema 校验在 E02b
    建立正式映射后再收严。
    """
    from evaluation.stance.scifact_data import load_corpus

    corpus = load_corpus(raw_dir / "corpus.jsonl")
    claims = _read_jsonl(raw_dir / f"claims_{split}.jsonl")
    gold_by_id = {
        str(row["id"]): _claim_gold_label(row, corpus)
        for row in claims
    }
    predictions = _read_jsonl(predictions_path)
    by_id = {str(row.get("id")): str(row.get("stance") or "").upper() for row in predictions}
    missing = sorted(set(gold_by_id) - set(by_id))
    if missing:
        raise SciFactDataError(f"missing predictions for {len(missing)} ids (e.g. {missing[:3]})")
    correct = sum(1 for claim_id, gold in gold_by_id.items() if by_id.get(claim_id) == gold)
    return {
        "mode": "scored",
        "split": split,
        "predictions": str(predictions_path),
        "claims": len(gold_by_id),
        "accuracy": round(correct / max(1, len(gold_by_id)), 6),
        "note": "仅供已批准的模型/检索映射评分；不宣称 L3 通过。",
    }


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _claim_gold_label(row: dict, corpus: dict[int, dict]) -> str:
    """SciFact 官方协议：有 SUPPORT 证据→SUPPORT；有 CONTRADICT 且无 SUPPORT→CONTRADICT；否则 NEUTRAL。"""
    evidence = row.get("evidence") or {}
    labels = {rationale["label"] for rationales in evidence.values() for rationale in rationales}
    if "SUPPORT" in labels:
        return "SUPPORT"
    if "CONTRADICT" in labels:
        return "CONTRADICT"
    return "NEUTRAL"


def main() -> None:
    parser = argparse.ArgumentParser(description="SciFact 锚点数据准入与 dry-run 评测入口")
    parser.add_argument("--split", choices=["train", "dev", "test"], default="dev")
    parser.add_argument("--raw-dir", type=Path, default=Path(DEFAULT_RAW_DIR))
    parser.add_argument("--predictions", type=Path, help="已批准的模型预测文件（与 --allow-score 同时使用才计算分数）")
    parser.add_argument("--allow-score", action="store_true", help="显式授权输出 benchmark 分数（默认不输出）")
    args = parser.parse_args()

    if args.predictions and not args.allow_score:
        print("拒绝：提供了 --predictions 但未提供 --allow-score；默认不做评分。", file=sys.stderr)
        sys.exit(2)
    if args.allow_score and not args.predictions:
        print("拒绝：--allow-score 需要 --predictions。", file=sys.stderr)
        sys.exit(2)

    try:
        if args.predictions:
            report = scored_run(args.raw_dir, args.split, args.predictions)
        else:
            report = dry_run(args.raw_dir, args.split)
    except SciFactDataError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
