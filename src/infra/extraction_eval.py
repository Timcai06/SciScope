"""D04 抽取质量评测聚合脚本（修订版，承接真实 20 篇盲审）。

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

程序只做聚合与对齐，不生成、不替代任何人工标注。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "extraction-eval/v2"

# D03 六类字段顺序。
FIELD_ORDER = ("study_population", "study_design", "main_result", "numeric_findings", "limitations", "conclusion")

JUDGMENTS = frozenset({"correct", "incorrect", "unsure"})


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
    structured: list[dict[str, Any]] = []
    src = Path(input_structured_path)
    if src.exists():
        with src.open("r", encoding="utf-8") as handle:
            structured = [json.loads(line) for line in handle if line.strip()]

    gold: list[dict[str, Any]] = []
    gold_src = Path(gold_path)
    if gold_src.exists():
        with gold_src.open("r", encoding="utf-8") as handle:
            gold = [json.loads(line) for line in handle if line.strip()]

    adjudications: list[dict[str, Any]] = []
    ad_src = Path(adjudication_path) if adjudication_path else None
    if ad_src is not None and ad_src.exists():
        with ad_src.open("r", encoding="utf-8") as handle:
            adjudications = [json.loads(line) for line in handle if line.strip()]

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
