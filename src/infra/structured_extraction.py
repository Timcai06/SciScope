"""D03 关键科学信息结构化抽取层。

在 D02 可追溯 chunk 之上，用**离线规则**抽取六类科学信息（不调用在线 LLM）：

1. ``study_population`` 研究对象
2. ``study_design``     研究设计/方法
3. ``main_result``      主要结果
4. ``numeric_findings`` 数值与单位
5. ``limitations``      限制条件
6. ``conclusion``       结论句

诚实边界（硬约束）：
- 每个非空字段必须带 provenance：来源 ``chunk_uid``、``locator``、原文
  ``sentence`` + ``span``（在 chunk 文本内的字符偏移）、抽取版本与置信度；
- 无法定位或低置信 → ``value`` 留空并标记 ``low_confidence``/``not_found``，
  候选句写入 ``candidates`` 供人工待审，**绝不编造确定值**；
- 证据句一律从 chunk.text 本身切出并回链定位；若定位失败（如文本被篡改），
  该字段降级为 ``low_confidence`` 且不输出值。

本层不改 TUI / MCP / Agent / 图谱 / 生产检索链；不做全量重建。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from src.infra.chunks import stable_uid

# schema 版本：所有输出与字段都携带。
SCHEMA_VERSION = "structured-extraction/v1"

# 字段固定顺序（对应 D03 目标 1-6）。
FIELD_ORDER = ("study_population", "study_design", "main_result", "numeric_findings", "limitations", "conclusion")

# 指示词（小写匹配）：字段 -> (强指示词, 一般指示词)。中英双语。
_FIELD_INDICATORS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "study_population": (
        ("randomized patients", "study population", "participants were"),
        (
            "patients", "participants", "subjects", "mice", "rats", "cells", "tissue",
            "samples", "population", "cohort", "患者", "参与者", "受试者", "小鼠",
            "大鼠", "细胞", "样本", "人群", "队列",
        ),
    ),
    "study_design": (
        (
            "randomized controlled", "randomised controlled", "double-blind",
            "case-control", "cross-sectional", "longitudinal study",
            "我们提出", "我们设计",
        ),
        (
            "randomized", "randomised", "controlled trial", "cohort study",
            "neural network", "transformer", "regression", "model", "method",
            "experiment", "we propose", "we used", "we design", "随机", "对照",
            "队列", "双盲", "横断面", "纵向", "模型", "神经网络", "回归", "实验", "方法",
        ),
    ),
    "main_result": (
        ("results show", "results indicate", "we found that", "结果表明", "我们发现"),
        (
            "we found", "our results", "outperforms", "improved", "significantly",
            "accuracy", "achieves", "demonstrate", "显著", "提升", "优于", "准确率",
            "达到", "结果显示", "实验表明",
        ),
    ),
    "limitations": (
        ("study limitations", "a limitation", "局限性"),
        (
            "limitation", "limitations", "however", "caveat", "we did not",
            "not considered", "further work", "shortcoming", "局限", "不足", "限制",
            "未能", "没有考虑", "仍需要", "未来工作",
        ),
    ),
    "conclusion": (
        ("in conclusion", "we conclude that", "our findings suggest", "综上所述", "我们得出结论"),
        ("conclude", "suggest that", "taken together", "研究表明", "本文表明", "总之"),
    ),
}

# 数值与单位提取：带单位数值 + p 值。
_NUMBER_UNIT_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*"
    r"(%|％|°C|℃|mg|kg|g|mL|ml|L|µg|μg|ng|pg|mm|cm|m|s|ms|h|wk|d|"
    r"years|months|weeks|days|岁|年|月|周|天|毫米|厘米|毫升|毫克|克)?"
)
_P_VALUE_RE = re.compile(r"p\s*[<≤=]\s*0?\.\d+")


@dataclass
class FieldEvidence:
    """字段证据：来源 chunk、定位、原文句与 span。"""

    chunk_uid: str
    locator: dict[str, Any]
    sentence: str
    span: dict[str, int]


@dataclass
class ExtractedField:
    """单字段抽取结果。``status`` ∈ extracted / not_found / low_confidence。"""

    field: str
    status: str
    value: Any
    confidence: float
    evidence: FieldEvidence | None = None
    candidates: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class ExtractionResult:
    """一篇论文（按 D02 chunks 聚合）的结构化抽取结果。

    ``invalid_chunks`` 记录被拒绝参与抽取的 chunk（来源链断裂：chunk_uid
    与按 D02 公式重算的结果不一致，或组内来源/哈希不一致），不静默丢弃。
    """

    schema_version: str
    paper_id: str
    source: str
    record_sha256: str
    fields: list[ExtractedField]
    invalid_chunks: list[dict[str, Any]] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _split_sentences(text: str) -> list[str]:
    """中英混合切句：按句号/问号/叹号/分号以及**换行**切分，保留原文子串。

    换行也作为句子边界，避免标题与摘要首句在无标点时被合并成一个句子。
    """
    cleaned = _clean(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?。！？;；])\s+|(?:\r?\n)+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def chunk_uid_matches(chunk: dict[str, Any]) -> bool:
    """按 D02 生成公式重算 chunk_uid，校验来源链是否完整。

    若 chunk 文本被篡改（与生成时不一致），重算结果将不等于 ``chunk_uid``，
    该 chunk 禁止参与抽取（HIGH-1 修复）。
    """
    expected = stable_uid(
        "trace-chunk",
        chunk.get("paper_id", ""),
        chunk.get("source", ""),
        chunk.get("record_sha256", ""),
        chunk.get("chunk_index"),
        chunk.get("chunk_type"),
        (chunk.get("locator") or {}).get("page", ""),
        chunk.get("text", ""),
    )
    return expected == chunk.get("chunk_uid")


def _sort_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 (chunk_index, chunk_uid) 稳定排序，保证输入顺序不影响抽取结果。"""

    def _key(chunk: dict[str, Any]) -> tuple[int, str]:
        try:
            index = int(chunk.get("chunk_index") or 0)
        except (TypeError, ValueError):
            index = 0
        return (index, str(chunk.get("chunk_uid") or ""))

    return sorted(chunks, key=_key)


def _locate_sentence(chunk_text: str, sentence: str) -> dict[str, int] | None:
    """在 chunk 文本中定位句子（首个命中），返回 {start_char, end_char}。

    找不到（例如句子来自被篡改的文本/外部注入）返回 None —— 调用方必须
    据此降级为 low_confidence，不得编造。
    """
    start = chunk_text.find(sentence)
    if start < 0:
        return None
    return {"start_char": start, "end_char": start + len(sentence)}


def _match_strength(sentence: str, strong: tuple[str, ...], weak: tuple[str, ...]) -> tuple[bool, float]:
    lowered = sentence.lower()
    if any(indicator in lowered for indicator in strong):
        return True, 0.8
    if any(indicator in lowered for indicator in weak):
        return True, 0.6
    return False, 0.0


def _extract_sentence_field(
    field: str,
    chunks: list[dict[str, Any]],
    strong: tuple[str, ...],
    weak: tuple[str, ...],
    *,
    abstract_fallback: bool = False,
) -> ExtractedField:
    """句子级字段抽取：扫描所有 chunk 的句子，取首个强/一般指示词命中。"""
    candidates: list[str] = []
    for chunk in chunks:
        chunk_text = _clean(chunk.get("text"))
        for sentence in _split_sentences(chunk_text):
            matched, confidence = _match_strength(sentence, strong, weak)
            if not matched:
                continue
            span = _locate_sentence(chunk_text, sentence)
            if span is None:
                # 句子定位失败（文本被篡改/异常）：不输出值，标记待审。
                return ExtractedField(
                    field=field,
                    status="low_confidence",
                    value="",
                    confidence=0.0,
                    reason="span_not_located_in_chunk",
                    candidates=[sentence],
                )
            return ExtractedField(
                field=field,
                status="extracted",
                value=sentence,
                confidence=confidence,
                evidence=FieldEvidence(
                    chunk_uid=_clean(chunk.get("chunk_uid")),
                    locator=chunk.get("locator") or {},
                    sentence=sentence,
                    span=span,
                ),
            )
        candidates.extend(sentence for sentence in _split_sentences(chunk_text))
    if abstract_fallback:
        # 结论回退：无指示词时取摘要/首个 chunk 的末句作候选（低置信，不输出确定值）。
        last_sentence = _split_sentences(_clean(chunks[0].get("text"))) if chunks else []
        if last_sentence:
            return ExtractedField(
                field=field,
                status="low_confidence",
                value="",
                confidence=0.4,
                reason="indicator_not_found_using_abstract_fallback",
                candidates=[last_sentence[-1]],
            )
    return ExtractedField(field=field, status="not_found", value="", confidence=0.0, candidates=candidates[:5])


def _extract_numeric(chunks: list[dict[str, Any]]) -> ExtractedField:
    """数值与单位抽取：扫描全部句子，收集带单位数值与 p 值。"""
    findings: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_text = _clean(chunk.get("text"))
        for sentence in _split_sentences(chunk_text):
            span = _locate_sentence(chunk_text, sentence)
            if span is None:
                continue  # 该句无法定位，跳过（不编造）
            matches: list[dict[str, Any]] = []
            for number, unit in _NUMBER_UNIT_RE.findall(sentence):
                # 数值发现必须是带单位或含小数的量；孤立整数（页码/编号等）不算，
                # 避免把 “Paper 1” 之类的噪声当数值证据。
                if unit or "." in number:
                    matches.append({"number": number, "unit": unit or ""})
            for p_value in _P_VALUE_RE.findall(sentence):
                matches.append({"number": p_value, "unit": "p-value"})
            if matches:
                findings.append(
                    {
                        "sentence": sentence,
                        "span": span,
                        "chunk_uid": _clean(chunk.get("chunk_uid")),
                        "locator": chunk.get("locator") or {},
                        "values": matches,
                    }
                )
    if not findings:
        return ExtractedField(field="numeric_findings", status="not_found", value=[], confidence=0.0)
    first = findings[0]
    return ExtractedField(
        field="numeric_findings",
        status="extracted",
        value=findings,
        confidence=0.7,
        evidence=FieldEvidence(
            chunk_uid=first["chunk_uid"],
            locator=first["locator"],
            sentence=first["sentence"],
            span=first["span"],
        ),
    )


def extract_from_chunks(chunks: list[dict[str, Any]], record: dict[str, Any] | None = None) -> ExtractionResult:
    """把一篇论文的 D02 chunks 抽取为结构化字段。

    ``chunks`` 为 D02 ``build_traceable_chunks`` 产物；``record`` 可选，用于
    paper_id/source/record_sha256 兜底（chunk 内已带这些字段）。

    安全与确定性（按评审修复）：
    - 先按 (chunk_index, chunk_uid) 排序，输入顺序不影响结果；
    - 按 D02 公式重算 chunk_uid，**来源链断裂的 chunk（文本被篡改）禁止参与抽取**，
      记入 ``invalid_chunks`` 供查询，绝不从被篡改文本产出确定值。
    """
    invalid_chunks: list[dict[str, Any]] = []
    valid_chunks = _sort_chunks(chunks)
    kept: list[dict[str, Any]] = []
    for chunk in valid_chunks:
        if not chunk_uid_matches(chunk):
            invalid_chunks.append(
                {
                    "chunk_uid": chunk.get("chunk_uid"),
                    "paper_id": chunk.get("paper_id"),
                    "source": chunk.get("source"),
                    "chunk_index": chunk.get("chunk_index"),
                    "reason": "chunk_uid_mismatch",
                }
            )
        else:
            kept.append(chunk)
    chunks = kept

    first = chunks[0] if chunks else {}
    paper_id = _clean(first.get("paper_id") or (record or {}).get("paper_id"))
    source = _clean(first.get("source") or (record or {}).get("source"))
    record_sha256 = _clean(first.get("record_sha256") or (record or {}).get("record_sha256"))

    fields: list[ExtractedField] = []
    for field_name in FIELD_ORDER:
        if field_name == "numeric_findings":
            fields.append(_extract_numeric(chunks))
            continue
        strong, weak = _FIELD_INDICATORS[field_name]
        fields.append(
            _extract_sentence_field(
                field_name,
                chunks,
                strong,
                weak,
                abstract_fallback=(field_name == "conclusion"),
            )
        )
    return ExtractionResult(
        schema_version=SCHEMA_VERSION,
        paper_id=paper_id,
        source=source,
        record_sha256=record_sha256,
        fields=fields,
        invalid_chunks=invalid_chunks,
    )


def _result_to_dict(result: ExtractionResult) -> dict[str, Any]:
    # 确定性输出：不含时间戳（extracted_at 移到运行级 summary），
    # 相同输入始终产生相同 structured 记录。
    payload: dict[str, Any] = asdict(result)
    payload["non_empty_fields"] = [
        f["field"] for f in payload["fields"] if f["status"] == "extracted"
    ]
    return payload


def run_structured_extraction(
    *,
    input_chunks_path: str | Path = "data/admission/traceable/chunks.jsonl",
    output_dir: str | Path = "data/admission/structured",
    output_file: str = "structured.jsonl",
    summary_file: str = "summary.json",
) -> dict[str, Any]:
    """端到端：读 D02 chunks.jsonl → 按 paper_id 聚合 → 抽取 → 写 structured/summary。

    输出在受控原始区（``data/admission/structured/``），不进入公开导出。
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_file
    summary_path = out_dir / summary_file

    by_paper: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    src = Path(input_chunks_path)
    if src.exists():
        with src.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                # HIGH-2 修复：按 (source, paper_id, record_sha256) 聚合，
                # 不同来源的同名 paper_id 绝不混入同一篇。
                key = (
                    str(chunk.get("source") or "unknown"),
                    str(chunk.get("paper_id") or "unknown"),
                    str(chunk.get("record_sha256") or ""),
                )
                by_paper.setdefault(key, []).append(chunk)

    status_counts: dict[str, int] = {}
    field_status: dict[str, dict[str, int]] = {}
    invalid_chunk_count = 0
    processed = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for key in sorted(by_paper):
            group = by_paper[key]
            # 组内一致性防御：chunk 的来源/论文/哈希必须与组键一致，否则单独记录。
            source, paper_id, record_sha256 = key
            consistent: list[dict[str, Any]] = []
            for chunk in group:
                if (
                    str(chunk.get("source") or "unknown") == source
                    and str(chunk.get("paper_id") or "unknown") == paper_id
                    and str(chunk.get("record_sha256") or "") == record_sha256
                ):
                    consistent.append(chunk)
                else:
                    invalid_chunk_count += 1
            result = extract_from_chunks(consistent)
            processed += 1
            invalid_chunk_count += len(result.invalid_chunks)
            handle.write(json.dumps(_result_to_dict(result), ensure_ascii=False, sort_keys=True) + "\n")
            for extracted_field in result.fields:
                status_counts[extracted_field.status] = status_counts.get(extracted_field.status, 0) + 1
                per_field = field_status.setdefault(extracted_field.field, {})
                per_field[extracted_field.status] = per_field.get(extracted_field.status, 0) + 1

    summary = {
        "schema_version": SCHEMA_VERSION,
        "extracted_at": _utc_now(),
        "input_chunks": sum(len(paper_chunks) for paper_chunks in by_paper.values()),
        "papers_processed": processed,
        "invalid_chunks": invalid_chunk_count,
        "field_status": {f: dict(sorted(by_status.items())) for f, by_status in sorted(field_status.items())},
        "status_counts": dict(sorted(status_counts.items())),
        "output_path": str(out_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
