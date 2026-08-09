"""D02 可追溯解析、切片与回链测试。

覆盖验收：
- 最小准入样例解析并产生带回链字段的 chunk；
- 失败样例写入可查询失败状态（不静默丢弃）；
- source_file_sha256 回链（有字节核验/无字节 unverified）、record_sha256 保留、
  定位字段（页码或文本范围）、解析器版本；
- 批处理端到端（chunks/failures/summary）。
"""

import hashlib
import json

from src.data_contracts.admission import compute_record_hash
from src.infra.traceable_chunks import (
    PARSER_VERSION,
    backtrace_chunk,
    build_traceable_chunks,
    run_traceable_chunking,
)


def _admitted_record(**overrides):
    """构造一条 D01 准入后的记录（含双哈希与治理元数据）。"""
    record = {
        "paper_id": "PX-002",
        "source": "iflytek",
        "license": "cc0",
        "language": "zh",
        "year": 2024,
        "usage_rights": "indexable",
        "source_file_sha256": "b" * 64,
        "title": "可追溯切片测试论文",
        "abstract": "本文验证解析与切片的可追溯性。",
        "full_text": (
            "第一章 引言。本文验证解析与切片的可追溯性。"
            "第二章 方法。我们把 D01 准入记录切为带回链字段的 chunk。"
            "第三章 结论。每个 chunk 都回链到来源与版本。"
        ),
        "record_sha256": "placeholder",
        "_sciscope_admission_schema": "ingest-contract/v1",
    }
    record.update(overrides)
    if "record_sha256" not in overrides or overrides.get("record_sha256") == "placeholder":
        record["record_sha256"] = compute_record_hash(record)
    return record


def _write_source_file(tmp_path, *, content: bytes = b"raw-pdf-bytes", sha256: str | None = None):
    path = tmp_path / "source.pdf"
    path.write_bytes(content)
    return path, sha256 or hashlib.sha256(content).hexdigest()


# --- 最小样例：带回链字段的 chunk ------------------------------------------


def test_minimal_record_produces_traceable_chunks(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
    )

    result = build_traceable_chunks(record)

    assert result.failures == []
    assert len(result.chunks) >= 2  # title_abstract + 至少 1 个 full_text
    for chunk in result.chunks:
        assert chunk["paper_id"] == "PX-002"
        assert chunk["source"] == "iflytek"
        assert chunk["source_file_sha256"] == source_sha
        assert chunk["record_sha256"] == record["record_sha256"]
        assert chunk["parser_version"] == PARSER_VERSION
        assert chunk["source_hash_verified"] is True
        assert chunk["record_hash_verified"] is True


def test_full_text_chunks_carry_char_span(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(source_file_sha256=source_sha, _sciscope_source_path=str(source_path))

    result = build_traceable_chunks(record)

    full_text_chunks = [c for c in result.chunks if c["chunk_type"] == "full_text"]
    assert full_text_chunks, "应有 full_text 切片"
    for chunk in full_text_chunks:
        locator = chunk["locator"]
        assert locator["base"] == "normalized_text"
        assert isinstance(locator["start_char"], int)
        assert isinstance(locator["end_char"], int)
        assert 0 <= locator["start_char"] < locator["end_char"]
        assert chunk["source_field"] == "full_text"


def test_title_abstract_chunk_has_field_locator(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(source_file_sha256=source_sha, _sciscope_source_path=str(source_path))

    result = build_traceable_chunks(record)

    ta = [c for c in result.chunks if c["chunk_type"] == "title_abstract"]
    assert len(ta) == 1
    assert ta[0]["locator"]["field"] == "title+abstract"
    assert ta[0]["source_field"] == "title+abstract"


def test_paged_full_text_carries_page_locator(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        full_text="",
        full_text_pages=[
            {"page": 1, "text": "第一页内容。可追溯切片。",
             "extra": "忽略的页元数据"},
            {"page": 2, "text": "第二页内容。回链字段。",
             "extra": "忽略的页元数据"},
        ],
    )

    result = build_traceable_chunks(record)

    page_chunks = [c for c in result.chunks if c["chunk_type"] == "full_text_page"]
    assert len(page_chunks) == 2
    pages = {c["locator"]["page"] for c in page_chunks}
    assert pages == {1, 2}
    for chunk in page_chunks:
        assert chunk["source_field"].startswith("full_text:page:")
        assert chunk["locator"]["base"] == "normalized_page_text"


def test_paged_web_noise_not_chunked_and_recorded(tmp_path):
    # 评审复现场景：分页正文中的网页噪声不得被切片，必须写入失败状态。
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        full_text="",
        full_text_pages=[{"page": 1, "text": "Access denied. Enable JavaScript and reload the page."}],
    )

    result = build_traceable_chunks(record)

    assert not [c for c in result.chunks if c["chunk_type"] == "full_text_page"]
    assert any(f["status"] == "invalid_full_text_source" for f in result.failures)
    assert any("网页噪声" in f["reason"] or "第 1 页" in f["reason"] for f in result.failures)


def test_paged_pdf_garbage_not_chunked_and_recorded(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        full_text="",
        full_text_pages=[{"page": 1, "text": "%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\ntrailer"}],
    )

    result = build_traceable_chunks(record)

    assert not [c for c in result.chunks if c["chunk_type"] == "full_text_page"]
    assert any(f["status"] == "invalid_full_text_source" for f in result.failures)


def test_mixed_pages_only_noisy_page_fails(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        full_text="",
        full_text_pages=[
            {"page": 1, "text": "正常第一页内容。可追溯切片。"},
            {"page": 2, "text": "Access denied. Enable JavaScript and reload the page."},
        ],
    )

    result = build_traceable_chunks(record)

    page_chunks = [c for c in result.chunks if c["chunk_type"] == "full_text_page"]
    # 只有正常页被切片；噪声页不切片且记录失败。
    assert {c["locator"]["page"] for c in page_chunks} == {1}
    assert any(
        f["status"] == "invalid_full_text_source" and "第 2 页" in f["reason"]
        for f in result.failures
    )


# --- 失败样例：可查询状态，不静默丢弃 --------------------------------------


def test_pdf_garbage_full_text_is_not_chunked_and_recorded(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        full_text="%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 5\ntrailer",
    )

    result = build_traceable_chunks(record)

    assert not [c for c in result.chunks if c["chunk_type"] == "full_text"]
    assert any(f["status"] == "invalid_full_text_source" for f in result.failures)


def test_web_noise_full_text_is_not_chunked_and_recorded(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        full_text="Access denied. Enable JavaScript and reload the page.",
    )

    result = build_traceable_chunks(record)

    assert not [c for c in result.chunks if c["chunk_type"] == "full_text"]
    assert any(f["status"] == "invalid_full_text_source" for f in result.failures)


def test_missing_core_fields_is_recorded(tmp_path):
    record = _admitted_record()
    del record["source_file_sha256"]
    del record["record_sha256"]

    result = build_traceable_chunks(record)

    assert result.chunks == []
    assert any(f["status"] == "missing_core_fields" for f in result.failures)


def test_record_hash_mismatch_is_recorded(tmp_path):
    record = _admitted_record(record_sha256="0" * 64)

    result = build_traceable_chunks(record)

    assert result.chunks == []
    assert any(f["status"] == "record_hash_mismatch" for f in result.failures)


def test_no_full_text_is_queryable_not_silent(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(source_file_sha256=source_sha, _sciscope_source_path=str(source_path), full_text="")

    result = build_traceable_chunks(record)

    # 摘要切片仍可产出，但无全文的状态必须可查询。
    assert any(c["chunk_type"] == "title_abstract" for c in result.chunks)
    assert any(f["status"] == "no_full_text" for f in result.failures)


# --- source_file_sha256 核验（硬约束 6） -------------------------------------


def test_source_hash_verified_when_bytes_match(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(source_file_sha256=source_sha, _sciscope_source_path=str(source_path))

    result = build_traceable_chunks(record)

    assert all(c["source_hash_verified"] is True for c in result.chunks)
    assert all(c["source_hash_status"] == "verified" for c in result.chunks)


def test_source_hash_mismatch_is_recorded(tmp_path):
    source_path, _ = _write_source_file(tmp_path)
    record = _admitted_record(source_file_sha256="c" * 64, _sciscope_source_path=str(source_path))

    result = build_traceable_chunks(record)

    assert all(c["source_hash_verified"] is False for c in result.chunks)
    assert all(c["source_hash_status"] == "mismatch" for c in result.chunks)
    assert any("sha256_mismatch" in c["source_hash_reason"] for c in result.chunks)


def test_source_hash_unverified_when_bytes_unavailable(tmp_path):
    # 无原始字节（未提供定位路径）→ 必须 unverified，绝不伪称通过。
    record = _admitted_record()

    result = build_traceable_chunks(record)

    assert all(c["source_hash_verified"] is False for c in result.chunks)
    assert all(c["source_hash_status"] == "unverified" for c in result.chunks)
    assert any(c["source_hash_reason"] == "source_bytes_unavailable" for c in result.chunks)


def test_source_hash_unverified_when_file_missing(tmp_path):
    record = _admitted_record(_sciscope_source_path=str(tmp_path / "missing.pdf"))

    result = build_traceable_chunks(record)

    assert all(c["source_hash_status"] == "unverified" for c in result.chunks)
    assert any("source_file_not_found" in c["source_hash_reason"] for c in result.chunks)


# --- 回链抽查辅助（20 篇人工回链证据的工具） --------------------------------


def test_backtrace_chunk_verifies_all_locator_kinds(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        full_text_pages=[{"page": 1, "text": "第一页内容。可追溯切片。"}],
        full_text="",
    )

    result = build_traceable_chunks(record)
    assert result.chunks, "分页记录应产出 chunk"

    for chunk in result.chunks:
        check = backtrace_chunk(chunk, record)
        assert check["ok"] is True, f"{chunk['chunk_uid']}: {check['reason']}"
        assert check["actual_text"] == chunk["text"]
        assert check["paper_id"] == "PX-002"


def test_backtrace_chunk_detects_span_mismatch(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    record = _admitted_record(source_file_sha256=source_sha, _sciscope_source_path=str(source_path))

    result = build_traceable_chunks(record)
    full_text_chunk = next(c for c in result.chunks if c["chunk_type"] == "full_text")

    # 篡改记录全文（在开头插入改变偏移）→ span 回链必须失败（可查询），
    # 说明原文与 chunk 不再一致。
    tampered = dict(record)
    tampered["full_text"] = "前置插入改变偏移。 " + record["full_text"]
    check = backtrace_chunk(full_text_chunk, tampered)
    assert check["ok"] is False
    assert "span_mismatch" in check["reason"]


# --- 批处理端到端 -----------------------------------------------------------


def test_run_traceable_chunking_end_to_end(tmp_path):
    source_path, source_sha = _write_source_file(tmp_path)
    good = _admitted_record(
        source_file_sha256=source_sha,
        _sciscope_source_path=str(source_path),
        paper_id="PX-GOOD",
    )
    bad = _admitted_record(
        full_text="%PDF-1.4\nxref\n0 5\ntrailer",
        paper_id="PX-BAD",
    )
    input_file = tmp_path / "staged.jsonl"
    input_file.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in (good, bad)) + "\n",
        encoding="utf-8",
    )

    summary = run_traceable_chunking(input_path=input_file, output_dir=tmp_path / "out")

    chunks = [json.loads(line) for line in (tmp_path / "out" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    failures = [json.loads(line) for line in (tmp_path / "out" / "failures.jsonl").read_text(encoding="utf-8").splitlines()]

    assert summary["input_records"] == 2
    assert summary["chunks"] == len(chunks)
    assert summary["parser_version"] == PARSER_VERSION
    # PX-BAD 的 full_text 是 PDF 垃圾 → 不产生 full_text chunk，写入失败。
    assert "PX-BAD" in {c["paper_id"] for c in chunks}
    assert not [c for c in chunks if c["paper_id"] == "PX-BAD" and c["chunk_type"] == "full_text"]
    assert any(f["paper_id"] == "PX-BAD" and f["status"] == "invalid_full_text_source" for f in failures)
    assert any(f["paper_id"] == "PX-BAD" for f in failures)
    # summary 统计一致。
    assert summary["failures"] == len(failures)
