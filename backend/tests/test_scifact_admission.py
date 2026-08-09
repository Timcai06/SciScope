"""SciFact 锚点数据准入与 dry-run 入口测试（E02a）。

覆盖：
- 哈希不符、缺文件、schema 不符、引用缺失 → fail-closed；
- 统计输出（样本数、标签分布、缺失率、引用可解析率）；
- dry-run 默认不输出分数；评分路径需要 --predictions + --allow-score 同时满足。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.stance import scifact_data, scifact_eval

# ---- 最小 fixture：2 条 corpus + 2 条 claims（1 有证据 1 无）----


def _make_raw(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    raw = tmp_path / "raw"
    raw.mkdir()
    corpus = [
        {"doc_id": 1, "title": "T1", "abstract": ["sentence one.", "sentence two."], "structured": False},
        {"doc_id": 2, "title": "T2", "abstract": ["only sentence."], "structured": True},
    ]
    claims_dev = [
        {
            "id": 1,
            "claim": "Coffee reduces CVD risk.",
            "evidence": {"1": [{"label": "SUPPORT", "sentences": [0, 1]}]},
            "cited_doc_ids": [1],
        },
        {"id": 2, "claim": "No evidence claim.", "evidence": {}, "cited_doc_ids": []},
    ]
    (raw / "corpus.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in corpus), encoding="utf-8")
    (raw / "claims_dev.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims_dev), encoding="utf-8")
    # 在篡改/删除前固定哈希。
    from evaluation.stance.scifact_data import _sha256

    expected = {name: _sha256(raw / name) for name in ("corpus.jsonl", "claims_dev.jsonl")}
    return raw, expected


def _rehash(raw: Path) -> dict[str, str]:
    from evaluation.stance.scifact_data import _sha256

    return {name: _sha256(raw / name) for name in ("corpus.jsonl", "claims_dev.jsonl")}


def test_dry_run_stats_ok(tmp_path: Path) -> None:
    raw, expected = _make_raw(tmp_path)
    stats = scifact_data.verify_split(raw, "dev", expected)
    assert stats.claims == 2
    assert stats.claims_with_evidence == 1
    assert stats.evidence_missing_rate == 0.5
    assert stats.label_distribution == {"SUPPORT": 1, "NEUTRAL": 1}
    assert stats.doc_ref_resolvable_rate == 1.0
    assert stats.sentence_ref_valid_rate == 1.0
    assert stats.corpus_docs == 2


def test_missing_file_fails_closed(tmp_path: Path) -> None:
    raw, expected = _make_raw(tmp_path)
    (raw / "claims_dev.jsonl").unlink()
    with pytest.raises(scifact_data.SciFactDataError, match="missing file"):
        scifact_data.verify_split(raw, "dev", expected)


def test_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    raw, expected = _make_raw(tmp_path)
    (raw / "corpus.jsonl").write_text("tampered", encoding="utf-8")
    with pytest.raises(scifact_data.SciFactDataError, match="SHA256 mismatch"):
        scifact_data.verify_split(raw, "dev", expected)


def test_missing_claim_field_fails_closed(tmp_path: Path) -> None:
    raw, expected = _make_raw(tmp_path)
    (raw / "claims_dev.jsonl").write_text(
        json.dumps({"id": 1, "claim": "no evidence key"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    expected = _rehash(raw)
    with pytest.raises(scifact_data.SciFactDataError, match="missing claim fields"):
        scifact_data.verify_split(raw, "dev", expected)


def test_unresolvable_doc_ref_fails_closed(tmp_path: Path) -> None:
    raw, expected = _make_raw(tmp_path)
    rows = [json.loads(l) for l in (raw / "claims_dev.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows[0]["evidence"] = {"999": [{"label": "SUPPORT", "sentences": [0]}]}
    (raw / "claims_dev.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    expected = _rehash(raw)
    with pytest.raises(scifact_data.SciFactDataError, match="missing from corpus"):
        scifact_data.verify_split(raw, "dev", expected)


def test_out_of_bounds_sentence_fails_closed(tmp_path: Path) -> None:
    raw, expected = _make_raw(tmp_path)
    rows = [json.loads(l) for l in (raw / "claims_dev.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows[0]["evidence"] = {"1": [{"label": "SUPPORT", "sentences": [99]}]}
    (raw / "claims_dev.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    expected = _rehash(raw)
    with pytest.raises(scifact_data.SciFactDataError, match="out of abstract bounds"):
        scifact_data.verify_split(raw, "dev", expected)


def test_invalid_rationale_label_fails_closed(tmp_path: Path) -> None:
    raw, expected = _make_raw(tmp_path)
    rows = [json.loads(l) for l in (raw / "claims_dev.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows[0]["evidence"] = {"1": [{"label": "AGREE", "sentences": [0]}]}
    (raw / "claims_dev.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    expected = _rehash(raw)
    with pytest.raises(scifact_data.SciFactDataError, match="invalid rationale label"):
        scifact_data.verify_split(raw, "dev", expected)


def test_dry_run_entry_reports_no_score(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw, expected = _make_raw(tmp_path)
    monkeypatch.setattr(scifact_eval, "DEFAULT_RAW_DIR", str(raw))
    report = scifact_eval.dry_run(raw, "dev", expected)
    assert report["mode"] == "dry-run"
    assert report["status"] == "data_ok"
    assert "accuracy" not in report


def test_scored_run_needs_predictions_and_allow_score(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    raw, _expected = _make_raw(tmp_path)
    # --predictions 而无 --allow-score → 拒绝（exit 2）
    preds = tmp_path / "preds.jsonl"
    preds.write_text(json.dumps({"id": 1, "stance": "SUPPORT"}) + "\n" + json.dumps({"id": 2, "stance": "NEUTRAL"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["scifact_eval", "--raw-dir", str(raw), "--split", "dev", "--predictions", str(preds)])
    with pytest.raises(SystemExit) as exc:
        scifact_eval.main()
    assert exc.value.code == 2
    assert "未提供 --allow-score" in capsys.readouterr().err
    # --allow-score 而无 --predictions → 拒绝（exit 2）
    monkeypatch.setattr(sys, "argv", ["scifact_eval", "--raw-dir", str(raw), "--split", "dev", "--allow-score"])
    with pytest.raises(SystemExit) as exc:
        scifact_eval.main()
    assert exc.value.code == 2
