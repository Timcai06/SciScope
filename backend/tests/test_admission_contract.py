"""D01 受控摄取数据合同测试。

覆盖验收要求：
- 一份最小样例能通过合同并导入（写入受控暂存区）；
- 三种非法样例（缺来源、哈希不符、许可未知）被拒绝；
- 拒绝原因写入可查询日志；
- 双哈希语义：source_file_sha256（原始交付文件字节哈希，仅格式校验）与
  record_sha256（规范化记录哈希，必须与内容一致）；
- retracted 必须为布尔、correction 必须为字符串。
"""

import json

from src.data_contracts.admission import (
    STAGED_FILE,
    REJECTION_FILE,
    compute_record_hash,
    ingest_record,
    validate_ingest_record,
)

# 原始交付文件字节哈希：任意 64 位 hex（本模块无法验证原始文件内容，只校验格式）。
FAKE_SOURCE_FILE_SHA256 = "a" * 64


def _valid_record(**overrides):
    record = {
        "paper_id": "PX-001",
        "source": "iflytek",
        "license": "cc0",
        "language": "zh",
        "year": 2024,
        "usage_rights": "indexable",
        "source_file_sha256": FAKE_SOURCE_FILE_SHA256,
        "title": "最小合法样例",
    }
    record.update(overrides)
    if "record_sha256" not in overrides:
        record["record_sha256"] = compute_record_hash(record)
    return record


# --- 合法导入 -------------------------------------------------------------


def test_minimal_valid_record_passes_and_imports(tmp_path):
    decision = ingest_record(_valid_record(), staged_dir=tmp_path)

    assert decision.accepted is True
    assert decision.rejections == []
    assert decision.record is not None
    assert decision.record["_sciscope_admission_schema"] == "ingest-contract/v1"

    staged = tmp_path / STAGED_FILE
    assert staged.exists()
    lines = [json.loads(line) for line in staged.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["paper_id"] == "PX-001"
    assert lines[0]["source"] == "iflytek"
    assert lines[0]["source_file_sha256"] == FAKE_SOURCE_FILE_SHA256


def test_valid_record_can_be_loaded_back(tmp_path):
    decision = ingest_record(_valid_record(), staged_dir=tmp_path)
    staged = tmp_path / STAGED_FILE
    loaded = json.loads(staged.read_text(encoding="utf-8").splitlines()[0])
    # 正文载荷原样保留，治理元数据追加。
    assert loaded["title"] == "最小合法样例"
    assert loaded["_sciscope_admission_schema"] == "ingest-contract/v1"


# --- 三种非法样例 ----------------------------------------------------------


def test_reject_missing_source(tmp_path):
    record = _valid_record()
    del record["source"]

    decision = ingest_record(record, staged_dir=tmp_path)

    assert decision.accepted is False
    assert any(r.field == "source" and r.reason == "missing_or_empty" for r in decision.rejections)
    assert not (tmp_path / STAGED_FILE).exists()


def test_reject_unknown_license(tmp_path):
    # 许可未知 = 缺失/空（missing_or_empty）或显式 unknown 类值（unknown_license）。
    for bad, expected_reason in (
        ("unknown", "unknown_license"),
        ("UNKNOWN", "unknown_license"),
        ("n/a", "unknown_license"),
        ("", "missing_or_empty"),
        (None, "missing_or_empty"),
    ):
        record = _valid_record(license=bad)

        decision = ingest_record(record, staged_dir=tmp_path)

        assert decision.accepted is False, f"license={bad!r} 应被拒绝"
        assert any(
            r.field == "license" and r.reason == expected_reason for r in decision.rejections
        ), f"license={bad!r} 期望 {expected_reason}，实际 {decision.reasons}"
    assert not (tmp_path / STAGED_FILE).exists()


def test_reject_record_hash_mismatch(tmp_path):
    # record_sha256 与规范化记录内容不一致 → 哈希不符。
    record = _valid_record()
    record["record_sha256"] = "0" * 64

    decision = ingest_record(record, staged_dir=tmp_path)

    assert decision.accepted is False
    assert any(r.field == "record_sha256" and r.reason == "hash_mismatch" for r in decision.rejections)
    assert not (tmp_path / STAGED_FILE).exists()


# --- 双哈希语义 ------------------------------------------------------------


def test_source_file_sha256_required_and_format_only(tmp_path):
    # 缺失 → 拒绝。
    record = _valid_record()
    del record["source_file_sha256"]
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is False
    assert any(
        r.field == "source_file_sha256" and r.reason == "missing_or_empty"
        for r in decision.rejections
    )

    # 非 hex → 拒绝。
    record = _valid_record(source_file_sha256="not-a-sha256")
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is False
    assert any(
        r.field == "source_file_sha256" and r.reason == "not_sha256_hex"
        for r in decision.rejections
    )

    # 格式合法即通过（模块无原始文件字节，只做格式校验，内容回链由 D02 核验）。
    record = _valid_record(source_file_sha256="f" * 64)
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is True


def test_record_sha256_required(tmp_path):
    record = _valid_record()
    del record["record_sha256"]
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is False
    assert any(
        r.field == "record_sha256" and r.reason == "missing_or_empty" for r in decision.rejections
    )


def test_record_hash_is_stable_and_excludes_metadata_and_hashes():
    record = _valid_record()
    h1 = compute_record_hash(record)
    # 治理元数据、两个哈希字段自身都不改变内容哈希。
    record["_sciscope_admission_schema"] = "ingest-contract/v1"
    record["_sciscope_admitted_at"] = "2026-08-05T00:00:00+00:00"
    h2 = compute_record_hash(record)
    assert h1 == h2


# --- 拒绝日志 --------------------------------------------------------------


def test_rejections_are_logged_with_reasons(tmp_path):
    record = _valid_record(source=None, license="unknown")
    record["record_sha256"] = "0" * 64

    decision = ingest_record(record, staged_dir=tmp_path)

    assert decision.accepted is False
    log = tmp_path / REJECTION_FILE
    assert log.exists()
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["ts"]
    assert entry["record"]["paper_id"] == "PX-001"
    fields = {item["field"] for item in entry["rejections"]}
    assert {"source", "license", "record_sha256"} <= fields


# --- retracted / correction 类型校验 ----------------------------------------


def test_retracted_must_be_boolean(tmp_path):
    for bad in ("yes", "true", 1, 0, "1"):
        record = _valid_record(retracted=bad)
        decision = ingest_record(record, staged_dir=tmp_path)
        assert decision.accepted is False, f"retracted={bad!r} 应被拒绝"
        assert any(r.field == "retracted" and r.reason == "not_boolean" for r in decision.rejections)

    # 合法布尔值通过。
    record = _valid_record(retracted=True)
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is True


def test_correction_must_be_string(tmp_path):
    for bad in (123, True, ["errata"], None):
        record = _valid_record(correction=bad)
        decision = ingest_record(record, staged_dir=tmp_path)
        assert decision.accepted is False, f"correction={bad!r} 应被拒绝"
        assert any(r.field == "correction" and r.reason == "not_string" for r in decision.rejections)

    # 合法字符串通过。
    record = _valid_record(correction="补正：作者单位更正")
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is True


# --- 其余合同点 ------------------------------------------------------------


def test_reject_bad_paper_id(tmp_path):
    for bad in ("", "有空格 id", "id/with/slash"):
        record = _valid_record(paper_id=bad)
        decision = ingest_record(record, staged_dir=tmp_path)
        assert decision.accepted is False, f"paper_id={bad!r} 应被拒绝"
        assert any(r.field == "paper_id" for r in decision.rejections)


def test_reject_missing_language_and_bad_year(tmp_path):
    record = _valid_record()
    del record["language"]
    record["year"] = "not-a-year"
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is False
    assert any(r.field == "language" for r in decision.rejections)
    assert any(r.field == "year" and r.reason == "not_an_integer" for r in decision.rejections)


def test_reject_invalid_usage_rights(tmp_path):
    record = _valid_record(usage_rights="publish-everywhere")
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is False
    assert any(r.field == "usage_rights" for r in decision.rejections)


def test_redistributable_requires_permissive_license(tmp_path):
    record = _valid_record(usage_rights="redistributable", license="cc-by")
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is False
    assert any(
        r.field == "usage_rights" and r.reason == "license_not_redistributable"
        for r in decision.rejections
    )


def test_redistributable_allowed_for_cc0(tmp_path):
    record = _valid_record(usage_rights="redistributable", license="cc0")
    decision = ingest_record(record, staged_dir=tmp_path)
    assert decision.accepted is True
    assert (tmp_path / STAGED_FILE).exists()


def test_validate_is_pure_and_deterministic():
    record = _valid_record()
    first = validate_ingest_record(record)
    second = validate_ingest_record(record)
    assert first.accepted == second.accepted is True
    assert first.reasons == second.reasons
