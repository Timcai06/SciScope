"""D02 可追溯解析、切片与回链中间层。

把 D01 已准入的记录（``data/admission/staged.jsonl``）变成**可追溯的切片中间层**：
每个 chunk 都回链到 paper_id / source / source_file_sha256 / record_sha256 /
原始文件定位信息 / 解析器版本 / 页码或文本范围。

硬约束（对应 D02 计划与验收）：
- 不把 PDF 网页噪声、提示词或无定位文本当正文（复用 ``chunks.looks_like_pdf_garbage``
  并识别浏览器验证噪声）；
- 解析失败写入可查询失败文件（``failures.jsonl``），不静默丢弃；
- ``source_file_sha256`` 仅在可获得原始字节时核验；拿不到字节时记录为
  ``unverified``，绝不伪称通过；
- ``record_sha256`` 保留并在切片时复核（``record_hash_verified``）。

本层不重新下载/解析 PDF（全量富化与 embedding 属 2080 Ti 任务）；它把**已有正文**
组织为带回链与定位的切片，解析器版本即本层版本。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.data_contracts.admission import compute_record_hash
from src.infra.chunks import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    estimate_tokens,
    looks_like_pdf_garbage,
    stable_uid,
)

# 本层解析器版本：每个 chunk 与失败记录都携带，方便审计抽取版本。
PARSER_VERSION = "traceable-chunks/v1"

# 不可当正文的网页噪声特征（浏览器验证/拒绝访问/JS 提示）。
_WEB_NOISE_MARKERS = (
    "performing security verification",
    "verify that you're not a robot",
    "enable javascript and then reload the page",
    "access denied",
    "captcha",
)

DEFAULT_CHUNKS_FILE = "chunks.jsonl"
DEFAULT_FAILURES_FILE = "failures.jsonl"
DEFAULT_SUMMARY_FILE = "summary.json"


@dataclass
class ChunkingResult:
    """单条记录的切片结果：chunks 与可查询失败状态。"""

    paper_id: str
    source: str
    record_sha256: str
    chunks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SourceVerification:
    """原始文件字节哈希核验结果（硬约束 6）。"""

    verified: bool
    status: str  # verified | unverified | mismatch
    reason: str
    path: str = ""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _looks_like_web_noise(text: str) -> bool:
    lowered = str(text or "")[:4000].lower()
    return any(marker in lowered for marker in _WEB_NOISE_MARKERS)


def _page_spans_from_pages(pages: Any) -> list[dict[str, Any]] | None:
    """记录若提供 ``full_text_pages``（[{page, text}]），返回带页码的页列表。"""
    if not isinstance(pages, list) or not pages:
        return None
    result: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_no = page.get("page")
        text = _clean(page.get("text"))
        if text and (isinstance(page_no, int) or (isinstance(page_no, str) and page_no.isdigit())):
            result.append({"page": int(page_no), "text": text})
    return result or None


def _split_with_spans(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    """按字符范围切分规范文本，返回 [{text, start_char, end_char}]。

    span 基于切分所用的规范化文本（空白折叠后），记录 base="normalized_text"，
    避免把原文偏移与规范文本偏移混为一谈。
    """
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [{"text": cleaned, "start_char": 0, "end_char": len(cleaned)}]

    spans: list[dict[str, Any]] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        if end < len(cleaned):
            sentence_end = max(cleaned.rfind(".", start, end), cleaned.rfind("。", start, end))
            if sentence_end > start + max_chars // 2:
                end = sentence_end + 1
        spans.append({"text": cleaned[start:end].strip(), "start_char": start, "end_char": end})
        if end >= len(cleaned):
            break
        start = max(0, end - overlap_chars)
    return [span for span in spans if span["text"]]


def _verify_source_file(record: dict[str, Any]) -> SourceVerification:
    """核验 source_file_sha256 与原始交付文件字节（硬约束 6）。

    - 记录提供可访问的原始文件定位（``_sciscope_source_path`` 或 ``source_file``）
      且文件存在 → 读字节比对：一致 verified / 不一致 mismatch；
    - 拿不到字节（无定位或文件不存在）→ unverified，绝不伪称通过。
    """
    expected = _clean(record.get("source_file_sha256"))
    location = _clean(record.get("_sciscope_source_path") or record.get("source_file"))
    if not location:
        return SourceVerification(False, "unverified", "source_bytes_unavailable")
    path = Path(location)
    if not path.is_file():
        return SourceVerification(False, "unverified", f"source_file_not_found:{location}")
    import hashlib

    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual == expected:
        return SourceVerification(True, "verified", "sha256_match", str(path))
    return SourceVerification(False, "mismatch", f"sha256_mismatch:expected={expected[:12]}…actual={actual[:12]}…", str(path))


def _normalize_page_text_for_span(page: dict[str, Any], span: dict[str, Any]) -> dict[str, Any]:
    """把页内 span 转成带 page 号的定位字段。"""
    return {
        "page": page["page"],
        "start_char": span["start_char"],
        "end_char": span["end_char"],
        "base": "normalized_page_text",
    }


def build_traceable_chunks(record: dict[str, Any]) -> ChunkingResult:
    """把一条 D01 准入记录解析为带回链字段的 chunk + 失败状态。

    输入预期为 D01 ``ingest_record`` 通过后的记录（含 ``source_file_sha256``、
    ``record_sha256``、``_sciscope_admission_schema`` 等）。
    """
    paper_id = _clean(record.get("paper_id"))
    source = _clean(record.get("source"))
    record_sha256 = _clean(record.get("record_sha256"))
    result = ChunkingResult(paper_id=paper_id, source=source, record_sha256=record_sha256)

    # 核心回链字段缺失 → 可查询失败，不产出 chunk。
    missing = [key for key in ("paper_id", "source", "record_sha256", "source_file_sha256") if not _clean(record.get(key))]
    if missing:
        result.failures.append(
            {
                "paper_id": paper_id,
                "source": source,
                "record_sha256": record_sha256,
                "status": "missing_core_fields",
                "reason": f"missing:{','.join(missing)}",
                "parser_version": PARSER_VERSION,
                "ts": _utc_now(),
            }
        )
        return result

    # record_sha256 复核（D01 已校验，D02 切片时再验一次，防中途篡改）。
    record_hash_verified = compute_record_hash(record) == record_sha256
    if not record_hash_verified:
        result.failures.append(
            {
                "paper_id": paper_id,
                "source": source,
                "record_sha256": record_sha256,
                "status": "record_hash_mismatch",
                "reason": "compute_record_hash(record) != record_sha256",
                "parser_version": PARSER_VERSION,
                "ts": _utc_now(),
            }
        )
        return result

    # source_file_sha256 核验（拿不到字节必须 unverified，不伪称通过）。
    source_check = _verify_source_file(record)

    base = {
        "paper_id": paper_id,
        "source": source,
        "source_file_sha256": _clean(record.get("source_file_sha256")),
        "record_sha256": record_sha256,
        "parser_version": PARSER_VERSION,
        "source_file": source_check.path,
        "source_hash_verified": source_check.verified,
        "source_hash_status": source_check.status,
        "source_hash_reason": source_check.reason,
        "record_hash_verified": record_hash_verified,
    }

    chunk_index = 0

    def _emit(chunk_type: str, source_field: str, text: str, span: dict[str, Any]) -> None:
        nonlocal chunk_index
        chunk_uid = stable_uid(
            "trace-chunk", paper_id, source, record_sha256, chunk_index, chunk_type, span.get("page", ""), text
        )
        chunk = {
            **base,
            "chunk_uid": chunk_uid,
            "chunk_index": chunk_index,
            "chunk_type": chunk_type,
            "source_field": source_field,
            "locator": span,
            "text": text,
            "token_estimate": estimate_tokens(text),
            "text_provenance": _clean(record.get("_sciscope_text_provenance") or "admission_record"),
        }
        result.chunks.append(chunk)
        chunk_index += 1

    # 1) 标题+摘要（字段级定位，无页码 → locator 描述字段范围）。
    title_abstract = "\n".join(
        part for part in (_clean(record.get("title")), _clean(record.get("abstract"))) if part
    )
    if title_abstract:
        _emit(
            "title_abstract",
            "title+abstract",
            title_abstract,
            {"field": "title+abstract", "start_char": 0, "end_char": len(title_abstract), "base": "field_text"},
        )
    else:
        result.failures.append(
            {
                "paper_id": paper_id,
                "source": source,
                "record_sha256": record_sha256,
                "status": "no_title_abstract",
                "reason": "title 与 abstract 均为空",
                "parser_version": PARSER_VERSION,
                "ts": _utc_now(),
            }
        )

    # 2) 全文：优先按页（full_text_pages），否则按规范文本字符范围。
    full_text = _clean(record.get("full_text"))
    pages = _page_spans_from_pages(record.get("full_text_pages"))
    if pages is not None:
        # 分页正文与纯文本走同一噪声/垃圾防线：
        # - PDF 结构垃圾是文档级失败信号 → 整页集合先拦截；
        # - 网页噪声（如 Access denied）可能只出现在个别页 → 逐页判定，
        #   命中页不切片并写入可查询失败，其余正常页照常切片。
        joined_pages = "\n".join(page["text"] for page in pages)
        if looks_like_pdf_garbage(joined_pages):
            result.failures.append(
                {
                    "paper_id": paper_id,
                    "source": source,
                    "record_sha256": record_sha256,
                    "status": "invalid_full_text_source",
                    "reason": "full_text_pages 整体为 PDF 结构垃圾或网页噪声（不切片）",
                    "parser_version": PARSER_VERSION,
                    "ts": _utc_now(),
                }
            )
        else:
            for page in pages:
                page_text = page["text"]
                if looks_like_pdf_garbage(page_text) or _looks_like_web_noise(page_text):
                    result.failures.append(
                        {
                            "paper_id": paper_id,
                            "source": source,
                            "record_sha256": record_sha256,
                            "status": "invalid_full_text_source",
                            "reason": f"full_text_pages 第 {page['page']} 页为 PDF 结构垃圾或网页噪声（不切片）",
                            "parser_version": PARSER_VERSION,
                            "ts": _utc_now(),
                        }
                    )
                    continue
                for span in _split_with_spans(page_text):
                    _emit(
                        "full_text_page",
                        f"full_text:page:{page['page']}",
                        span["text"],
                        _normalize_page_text_for_span(page, span),
                    )
    elif full_text:
        if looks_like_pdf_garbage(full_text) or _looks_like_web_noise(full_text):
            result.failures.append(
                {
                    "paper_id": paper_id,
                    "source": source,
                    "record_sha256": record_sha256,
                    "status": "invalid_full_text_source",
                    "reason": "full_text 为 PDF 结构垃圾或网页噪声（不切片）",
                    "parser_version": PARSER_VERSION,
                    "ts": _utc_now(),
                }
            )
        else:
            for span in _split_with_spans(full_text):
                _emit(
                    "full_text",
                    "full_text",
                    span["text"],
                    {"start_char": span["start_char"], "end_char": span["end_char"], "base": "normalized_text"},
                )
    else:
        # 无全文：可查询状态（论文可能只有摘要），不是静默丢失。
        result.failures.append(
            {
                "paper_id": paper_id,
                "source": source,
                "record_sha256": record_sha256,
                "status": "no_full_text",
                "reason": "记录未提供 full_text",
                "parser_version": PARSER_VERSION,
                "ts": _utc_now(),
            }
        )

    return result


def backtrace_chunk(chunk: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """按 chunk 的 locator 回链到记录中的原文位置，验证 span 一致性。

    这是 D02 验收「抽样 20 篇人工回链」的辅助工具：对给定 chunk，依据
    ``locator`` 从原始记录还原文本，与 ``chunk.text`` 比对，返回
    ``{ok, expected_text, actual_text, locator, reason}``。人工抽查时逐条核对
    ``ok`` 并记录抽查者与日期即可形成证据。
    """
    locator = chunk.get("locator") or {}
    base = locator.get("base")
    paper_id = chunk.get("paper_id") or record.get("paper_id") or ""
    source_text = ""
    label = ""

    if base == "field_text":
        field = locator.get("field") or "title+abstract"
        label = field
        if field == "title+abstract":
            source_text = "\n".join(
                part for part in (_clean(record.get("title")), _clean(record.get("abstract"))) if part
            )
        else:
            source_text = _clean(record.get(field))
    elif base == "normalized_text":
        label = "full_text"
        source_text = re.sub(r"\s+", " ", _clean(record.get("full_text"))).strip()
    elif base == "normalized_page_text":
        page = locator.get("page")
        label = f"full_text_pages:page:{page}"
        pages = _page_spans_from_pages(record.get("full_text_pages")) or []
        page_text = next((p["text"] for p in pages if p["page"] == page), "")
        source_text = re.sub(r"\s+", " ", page_text).strip()
    else:
        return {
            "ok": False,
            "expected_text": "",
            "actual_text": "",
            "locator": locator,
            "reason": f"unknown_locator_base:{base}",
        }

    start = int(locator.get("start_char") or 0)
    end = int(locator.get("end_char") or len(source_text))
    actual = source_text[start:end].strip()
    expected = str(chunk.get("text") or "")
    ok = actual == expected
    return {
        "ok": ok,
        "expected_text": expected,
        "actual_text": actual,
        "locator": locator,
        "reason": "" if ok else f"span_mismatch:{label}:{start}:{end}",
        "paper_id": paper_id,
        "source": chunk.get("source") or "",
        "chunk_uid": chunk.get("chunk_uid") or "",
    }


def run_traceable_chunking(
    *,
    input_path: str | Path = "data/admission/staged.jsonl",
    output_dir: str | Path = "data/admission/traceable",
    chunks_file: str = DEFAULT_CHUNKS_FILE,
    failures_file: str = DEFAULT_FAILURES_FILE,
    summary_file: str = DEFAULT_SUMMARY_FILE,
) -> dict[str, Any]:
    """批量把 D01 准入记录切为可追溯 chunk，并写 chunks/failures/summary。

    输出目录默认 ``data/admission/traceable/``（受控原始区内，避免混入公开导出）。
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = out_dir / chunks_file
    failures_path = out_dir / failures_file
    summary_path = out_dir / summary_file

    records: list[dict[str, Any]] = []
    src = Path(input_path)
    if src.exists():
        with src.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))

    total_chunks = 0
    failures_by_status: dict[str, int] = {}
    source_hash_status: dict[str, int] = {}
    record_hash_verified_count = 0
    chunk_types: dict[str, int] = {}

    with chunks_path.open("w", encoding="utf-8") as chunks_handle, failures_path.open("w", encoding="utf-8") as failures_handle:
        for record in records:
            result = build_traceable_chunks(record)
            for chunk in result.chunks:
                chunks_handle.write(json.dumps(chunk, ensure_ascii=False, sort_keys=True) + "\n")
                total_chunks += 1
                chunk_types[chunk["chunk_type"]] = chunk_types.get(chunk["chunk_type"], 0) + 1
                source_hash_status[chunk["source_hash_status"]] = source_hash_status.get(chunk["source_hash_status"], 0) + 1
                record_hash_verified_count += int(chunk["record_hash_verified"])
            for failure in result.failures:
                failures_handle.write(json.dumps(failure, ensure_ascii=False, sort_keys=True) + "\n")
                failures_by_status[failure["status"]] = failures_by_status.get(failure["status"], 0) + 1

    summary = {
        "parser_version": PARSER_VERSION,
        "input_records": len(records),
        "chunks": total_chunks,
        "chunks_by_type": dict(sorted(chunk_types.items())),
        "failures": sum(failures_by_status.values()),
        "failures_by_status": dict(sorted(failures_by_status.items())),
        "source_hash_status": dict(sorted(source_hash_status.items())),
        "record_hash_verified_records": record_hash_verified_count,
        "chunks_path": str(chunks_path),
        "failures_path": str(failures_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
