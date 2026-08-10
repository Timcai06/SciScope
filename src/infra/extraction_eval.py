"""D04 抽取评测：人工质量聚合与自动 silver 一致性审计。

把 D03 的结构化抽取结果（``structured.jsonl``）与**两阶段人工流程**产出对比：

- **阶段 A（盲审）**：盲审者只阅读原论文/可授权片段，产出 ``gold.jsonl``；
- **阶段 B（裁决）**：解除盲法后，对照 D03 输出逐字段人工裁决，产出
  ``adjudications.jsonl``（judgment ∈ correct/incorrect/unsure）。

诚实与 fail-closed 规则：

1. **唯一匹配**：gold 必须按 ``(source, paper_id, record_sha256)`` 唯一匹配 D03 记录；
   缺 ``record_sha256``、无对应记录、或同 ``(source, paper_id)`` 存在多条不同版本时，
   该 gold 条目**不可评测（unrateable）**并记录原因，**绝不任选一条**。
2. **正确率只来自人工裁决**：程序**不得**用字符串包含等模糊匹配自行判定“正确”
   （曾出现 ``1`` 匹配 ``10`` 的错误）；未提供 adjudication 时 ``correct=0`` 且标记
   ``pending_human_adjudication=True``。
3. **gold_locatable 真正参与评测**：盲审者判定“原文可定位”的样本，若 D03 证据
   span 无效 → 计 ``locatable_mismatch`` 并写入可复查失败例。

除人工聚合外，本模块还提供 ``evaluate_silver_consistency``：它以 D02 chunks
重新运行确定性的 D03 规则，并逐个校验输出字段的 provenance。这个检查只能证明
**同一实现可复现、输出可回链**，不能证明字段在原文语义上正确；因此它绝不产生
正确率，也不替代盲审或外部金标准。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.infra.structured_extraction import (
    SCHEMA_VERSION as STRUCTURED_SCHEMA_VERSION,
    _result_to_dict,
    chunk_uid_matches,
    extract_from_chunks,
)

SCHEMA_VERSION = "extraction-eval/v3"
SILVER_SCHEMA_VERSION = "extraction-silver-consistency/v1"

# D03 六类字段顺序。
FIELD_ORDER = ("study_population", "study_design", "main_result", "numeric_findings", "limitations", "conclusion")

JUDGMENTS = frozenset({"correct", "incorrect", "unsure"})
FIELD_STATUSES = frozenset({"extracted", "not_found", "low_confidence"})


def wilson_ci(positive: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson 95% 置信区间；total=0 返回 None（样本不足）。"""
    if total <= 0:
        return None
    p = positive / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


def _span_valid(evidence: dict[str, Any] | None) -> bool:
    if not evidence:
        return False
    span = evidence.get("span") or {}
    start = span.get("start_char")
    end = span.get("end_char")
    return isinstance(start, int) and isinstance(end, int) and start >= 0 and end > start


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


@dataclass
class FieldEval:
    """单字段聚合结果。``correct`` 只来自人工裁决（阶段 B）。

    ``correctness`` 的分母为**已裁决**可评测样本数（n - pending_count）：
    pending 样本尚未裁决，不当作错误计入。
    """

    field: str
    n: int
    extracted: int
    correct: int
    locatable: int
    gold_locatable_true: int
    locatable_mismatch: int
    rejected: int
    blank: int
    pending_count: int
    pending_human_adjudication: bool
    extraction_rate: float
    correctness: float
    locatable_rate: float
    rejected_rate: float
    blank_rate: float
    ci_low: float | None
    ci_high: float | None
    failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvalReport:
    schema_version: str
    paper_count: int
    gold_entries: int
    unrateable: list[dict[str, Any]]
    fields: list[FieldEval]


@dataclass
class SilverConsistencyReport:
    """自动化、非语义的 D04 silver 检查报告。

    ``technical_gate_pass`` 仅表示 D02→D03 的可复现性和证据回链都通过；它明确
    不是人工质量 PASS，也不能用于声称 precision/正确率。
    """

    schema_version: str
    structured_records: int
    source_chunk_groups: int
    reproducible_records: int
    provenance_checked_fields: int
    provenance_verified_fields: int
    unverifiable_records: int
    technical_gate_pass: bool
    evidence_level: str
    semantic_correctness_claimed: bool
    external_expert_gate_remaining: bool
    failures: list[dict[str, Any]] = field(default_factory=list)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _build_structured_index(structured_records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    """{(source, paper_id): {record_sha256: record}} —— 同论文多版本并存，绝不覆盖。"""
    index: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for record in structured_records:
        key = (_clean(record.get("source")) or "unknown", _clean(record.get("paper_id")) or "unknown")
        sha = _clean(record.get("record_sha256"))
        index.setdefault(key, {})[sha] = record
    return index


def _gold_key(gold: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean(gold.get("source")) or "unknown",
        _clean(gold.get("paper_id")) or "unknown",
        _clean(gold.get("record_sha256")),
    )


def _resolve_gold(
    gold: dict[str, Any],
    index: dict[tuple[str, str], dict[str, dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str | None]:
    """fail-closed 解析：缺 sha / 无记录 / 版本不匹配 → (None, reason)。"""
    source, paper_id, sha = _gold_key(gold)
    if not sha:
        return None, "missing_record_sha256"
    group = index.get((source, paper_id))
    if not group:
        return None, "no_structured_record"
    if sha not in group:
        versions = sorted(group)
        return None, f"record_sha256_no_match:available={len(versions)}"
    return group[sha], None


def evaluate_extraction(
    structured_records: list[dict[str, Any]],
    gold_records: list[dict[str, Any]],
    adjudications: list[dict[str, Any]] | None = None,
) -> EvalReport:
    """对比 D03 输出与两阶段人工产出，聚合每字段质量指标。

    ``gold_records`` 每条约：``{source, paper_id, record_sha256, field, gold_present,
    gold_value?, gold_locatable?, notes?}``；
    ``adjudications`` 每条约：``{source, paper_id, record_sha256, field, judgment, notes?}``。
    未提供 adjudications 时 ``correct=0`` 并标记 pending，程序不自行裁决。
    """
    index = _build_structured_index(structured_records)
    adjudication_map: dict[tuple[str, str, str, str], str] = {}
    for ad in adjudications or []:
        key = (*_gold_key(ad), _clean(ad.get("field")))
        judgment = _clean(ad.get("judgment"))
        if judgment in JUDGMENTS:
            adjudication_map[key] = judgment

    per_field: dict[str, dict[str, Any]] = {
        f: {
            "n": 0,
            "extracted": 0,
            "correct": 0,
            "locatable": 0,
            "gold_locatable_true": 0,
            "locatable_mismatch": 0,
            "rejected": 0,
            "blank": 0,
            "pending": False,
            "pending_count": 0,
            "failures": [],
        }
        for f in FIELD_ORDER
    }
    unrateable: list[dict[str, Any]] = []

    for gold in gold_records:
        field = _clean(gold.get("field"))
        if field not in per_field:
            continue
        acc = per_field[field]

        record, unrateable_reason = _resolve_gold(gold, index)
        if unrateable_reason is not None:
            # fail-closed：不可评测，绝不任选一条。
            unrateable.append(
                {
                    "source": gold.get("source"),
                    "paper_id": gold.get("paper_id"),
                    "record_sha256": gold.get("record_sha256"),
                    "field": field,
                    "reason": unrateable_reason,
                }
            )
            continue
        acc["n"] += 1

        extracted_field = next((f for f in record.get("fields", []) if f.get("field") == field), None)
        status = (extracted_field or {}).get("status")
        evidence = (extracted_field or {}).get("evidence")
        value = (extracted_field or {}).get("value")

        gold_present = bool(gold.get("gold_present", True))
        gold_locatable = gold.get("gold_locatable")

        if status == "extracted":
            acc["extracted"] += 1
            span_ok = _span_valid(evidence)
            if span_ok:
                acc["locatable"] += 1
            if gold_locatable is True and not span_ok:
                # 盲审者判定原文可定位，但 D03 证据 span 无效。
                acc["locatable_mismatch"] += 1
                acc["failures"].append(
                    {
                        "source": gold.get("source"),
                        "paper_id": gold.get("paper_id"),
                        "record_sha256": gold.get("record_sha256"),
                        "field": field,
                        "reason": "locatable_mismatch:human_locatable_but_span_invalid",
                        "actual_value": value,
                    }
                )
        else:
            if status == "not_found":
                acc["rejected"] += 1
            if status in ("not_found", "low_confidence") and not value:
                acc["blank"] += 1
            if gold_present:
                acc["failures"].append(
                    {
                        "source": gold.get("source"),
                        "paper_id": gold.get("paper_id"),
                        "record_sha256": gold.get("record_sha256"),
                        "field": field,
                        "reason": f"not_extracted:{status}",
                        "gold_value": gold.get("gold_value"),
                    }
                )

        if gold_locatable is True:
            acc["gold_locatable_true"] += 1

        # 正确性：只认人工裁决（阶段 B），程序不做模糊匹配；但存在一条硬规则——
        # 阶段 A 判定字段本不存在（gold_present=false）而系统抽取了 → **必为 false
        # positive**，人工裁决的 correct 不得覆盖指标（若裁决认为正确，须先回阶段 A
        # 更正 gold_present，再重评），防止“本不应存在的抽取”抬高正确率。
        judgment = adjudication_map.get((*_gold_key(gold), field))
        if status == "extracted" and gold_present is False:
            acc["failures"].append(
                {
                    "source": gold.get("source"),
                    "paper_id": gold.get("paper_id"),
                    "record_sha256": gold.get("record_sha256"),
                    "field": field,
                    "reason": "false_positive:gold_absent_but_extracted",
                    "actual_value": value,
                    "adjudication_note": "若裁决认为正确，请先回阶段 A 更正 gold_present=true 再重评",
                }
            )
            # 不计 correct，无论阶段 B 的 judgment 是什么。尚无阶段 B 裁决时，
            # 此样本仍是待裁决样本：不能把“已知是假阳性”偷换为“已经人工判错”，
            # 否则会错误进入 correctness 的已裁决分母。
            if judgment is None:
                acc["pending"] = True
                acc["pending_count"] += 1
        elif judgment is None:
            acc["pending"] = True
            acc["pending_count"] += 1
        elif judgment == "correct":
            acc["correct"] += 1
        else:
            acc["failures"].append(
                {
                    "source": gold.get("source"),
                    "paper_id": gold.get("paper_id"),
                    "record_sha256": gold.get("record_sha256"),
                    "field": field,
                    "reason": f"human_judged_{judgment}",
                    "gold_value": gold.get("gold_value"),
                }
            )

    fields_eval: list[FieldEval] = []
    for field_name in FIELD_ORDER:
        acc = per_field[field_name]
        n = acc["n"]
        pending_count = acc["pending_count"]
        # 正确率分母 = 已裁决可评测样本数（pending 未裁决，不当作错误）。
        adjudicated = n - pending_count
        ci = wilson_ci(acc["correct"], adjudicated) if adjudicated else None
        fields_eval.append(
            FieldEval(
                field=field_name,
                n=n,
                extracted=acc["extracted"],
                correct=acc["correct"],
                locatable=acc["locatable"],
                gold_locatable_true=acc["gold_locatable_true"],
                locatable_mismatch=acc["locatable_mismatch"],
                rejected=acc["rejected"],
                blank=acc["blank"],
                pending_count=pending_count,
                pending_human_adjudication=acc["pending"],
                extraction_rate=_rate(acc["extracted"], n),
                correctness=_rate(acc["correct"], adjudicated),
                locatable_rate=_rate(acc["locatable"], n),
                rejected_rate=_rate(acc["rejected"], n),
                blank_rate=_rate(acc["blank"], n),
                ci_low=ci[0] if ci else None,
                ci_high=ci[1] if ci else None,
                failures=acc["failures"],
            )
        )
    return EvalReport(
        schema_version=SCHEMA_VERSION,
        paper_count=len(index),
        gold_entries=len(gold_records),
        unrateable=unrateable,
        fields=fields_eval,
    )


def _record_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean(record.get("source")),
        _clean(record.get("paper_id")),
        _clean(record.get("record_sha256")),
    )


def _failure(record: dict[str, Any], check: str, reason: str, *, field_name: str | None = None) -> dict[str, Any]:
    """统一 silver 失败记录；保留可追溯 identity，绝不附会语义判断。"""
    source, paper_id, record_sha256 = _record_key(record)
    result: dict[str, Any] = {
        "source": source,
        "paper_id": paper_id,
        "record_sha256": record_sha256,
        "check": check,
        "reason": reason,
    }
    if field_name is not None:
        result["field"] = field_name
    return result


def evaluate_silver_consistency(
    structured_records: list[dict[str, Any]],
    traceable_chunks: list[dict[str, Any]],
) -> SilverConsistencyReport:
    """检查 D03 输出是否能从 D02 chunks 确定性重现，并逐字段验证 provenance。

    这是一个 **silver / 工程完整性** 门禁，不读取 gold、不做字符串近似匹配，也
    不判断抽取的科学含义。输入必须是同一受控批次的 D02 chunks 与 D03 输出；缺任
    一侧、重复 identity、schema/重现/证据回链失败都会令技术门禁失败。
    """
    failures: list[dict[str, Any]] = []
    chunks_by_record: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for chunk in traceable_chunks:
        key = _record_key(chunk)
        if not all(key):
            failures.append(_failure(chunk, "chunk_identity", "missing_source_paper_id_or_record_sha256"))
            continue
        chunks_by_record.setdefault(key, []).append(chunk)

    records_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicate_keys: set[tuple[str, str, str]] = set()
    for record in structured_records:
        key = _record_key(record)
        if not all(key):
            failures.append(_failure(record, "structured_identity", "missing_source_paper_id_or_record_sha256"))
            continue
        if key in records_by_key:
            duplicate_keys.add(key)
            failures.append(_failure(record, "structured_identity", "duplicate_structured_record"))
            continue
        records_by_key[key] = record

    reproducible_records = 0
    provenance_checked = 0
    provenance_verified = 0
    unverifiable_records = 0

    for key, record in records_by_key.items():
        if key in duplicate_keys:
            continue
        chunks = chunks_by_record.get(key)
        if not chunks:
            unverifiable_records += 1
            failures.append(_failure(record, "reproducibility", "no_matching_traceable_chunks"))
            continue
        if record.get("schema_version") != STRUCTURED_SCHEMA_VERSION:
            failures.append(
                _failure(record, "schema", f"expected={STRUCTURED_SCHEMA_VERSION}:actual={record.get('schema_version')}")
            )

        expected = _result_to_dict(extract_from_chunks(chunks))
        if record.get("fields") == expected["fields"] and record.get("invalid_chunks", []) == expected["invalid_chunks"]:
            reproducible_records += 1
        else:
            failures.append(_failure(record, "reproducibility", "d03_output_not_identical_to_deterministic_rerun"))

        fields = record.get("fields")
        if not isinstance(fields, list):
            failures.append(_failure(record, "field_shape", "fields_not_a_list"))
            continue
        seen_fields: set[str] = set()
        chunks_by_uid = {str(chunk.get("chunk_uid")): chunk for chunk in chunks}
        for extracted in fields:
            if not isinstance(extracted, dict):
                failures.append(_failure(record, "field_shape", "field_not_an_object"))
                continue
            field_name = _clean(extracted.get("field"))
            status = _clean(extracted.get("status"))
            if field_name not in FIELD_ORDER or field_name in seen_fields:
                failures.append(_failure(record, "field_shape", "unknown_or_duplicate_field", field_name=field_name))
                continue
            seen_fields.add(field_name)
            if status not in FIELD_STATUSES:
                failures.append(_failure(record, "field_shape", f"invalid_status:{status}", field_name=field_name))
                continue
            if status != "extracted":
                continue

            provenance_checked += 1
            evidence = extracted.get("evidence")
            if not isinstance(evidence, dict):
                failures.append(_failure(record, "provenance", "missing_evidence", field_name=field_name))
                continue
            chunk = chunks_by_uid.get(_clean(evidence.get("chunk_uid")))
            span = evidence.get("span") if isinstance(evidence.get("span"), dict) else {}
            start, end = span.get("start_char"), span.get("end_char")
            sentence = evidence.get("sentence")
            if not chunk:
                failures.append(_failure(record, "provenance", "evidence_chunk_not_in_same_record", field_name=field_name))
            elif not chunk_uid_matches(chunk):
                failures.append(_failure(record, "provenance", "evidence_chunk_uid_mismatch", field_name=field_name))
            elif not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
                failures.append(_failure(record, "provenance", "invalid_evidence_span", field_name=field_name))
            elif not isinstance(sentence, str) or chunk.get("text", "")[start:end] != sentence:
                failures.append(_failure(record, "provenance", "evidence_sentence_not_exact_span", field_name=field_name))
            elif evidence.get("locator") != (chunk.get("locator") or {}):
                failures.append(_failure(record, "provenance", "evidence_locator_not_equal_to_chunk", field_name=field_name))
            else:
                provenance_verified += 1
        if seen_fields != set(FIELD_ORDER):
            failures.append(_failure(record, "field_shape", "field_set_not_exactly_d03_six_fields"))

    for key, chunks in chunks_by_record.items():
        if key not in records_by_key:
            failures.append(_failure(chunks[0], "coverage", "traceable_chunks_have_no_structured_record"))

    return SilverConsistencyReport(
        schema_version=SILVER_SCHEMA_VERSION,
        structured_records=len(structured_records),
        source_chunk_groups=len(chunks_by_record),
        reproducible_records=reproducible_records,
        provenance_checked_fields=provenance_checked,
        provenance_verified_fields=provenance_verified,
        unverifiable_records=unverifiable_records,
        technical_gate_pass=bool(structured_records) and not failures,
        evidence_level="L2_automated_silver_reproducibility_and_provenance_only",
        semantic_correctness_claimed=False,
        external_expert_gate_remaining=True,
        failures=failures,
    )


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_silver_consistency_eval(
    *,
    input_structured_path: str | Path = "data/admission/structured/structured.jsonl",
    input_chunks_path: str | Path = "data/admission/traceable/chunks.jsonl",
    output_dir: str | Path = "data/admission/structured/eval",
    report_file: str = "silver_consistency_report.json",
) -> dict[str, Any]:
    """读同批 D02/D03 JSONL，写可复现的 silver 一致性报告。

    输出中不含时间戳，便于同输入复核。缺输入会产生失败报告，不能误报门禁通过。
    """
    structured = _read_jsonl(input_structured_path)
    chunks = _read_jsonl(input_chunks_path)
    report = evaluate_silver_consistency(structured, chunks)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / report_file
    report_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "schema_version": SILVER_SCHEMA_VERSION,
        "structured_records": len(structured),
        "traceable_chunks": len(chunks),
        "technical_gate_pass": report.technical_gate_pass,
        "report_path": str(report_path),
    }


def run_extraction_eval(
    *,
    input_structured_path: str | Path = "data/admission/structured/structured.jsonl",
    gold_path: str | Path = "data/admission/structured/gold.jsonl",
    adjudication_path: str | Path | None = "data/admission/structured/adjudications.jsonl",
    output_dir: str | Path = "data/admission/structured/eval",
    report_file: str = "eval_report.json",
) -> dict[str, Any]:
    """端到端评测：读 D03 structured + gold + adjudications → 聚合 → 写 eval_report。

    输出在受控原始区；report 内容确定性（时间戳只放 summary）。
    """
    structured = _read_jsonl(input_structured_path)
    gold = _read_jsonl(gold_path)
    adjudications = _read_jsonl(adjudication_path) if adjudication_path else []

    report = evaluate_extraction(structured, gold, adjudications)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / report_file
    report_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "structured_records": len(structured),
        "gold_entries": len(gold),
        "adjudications": len(adjudications),
        "unrateable": len(report.unrateable),
        "papers_in_report": report.paper_count,
        "report_path": str(report_path),
    }
    return summary
