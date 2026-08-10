"""Offline A03 QA regression over frozen deterministic fixtures.

This suite validates the actual `answer-contract/v1` implementation without
calling any online model. It keeps automated contract checks separate from
human review dimensions such as answer support and citation precision.

Outputs:
  - output/eval/qa_regression_report.json
  - output/eval/qa_regression_report.md
  - output/eval/qa_regression_manual_review_template.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.agent.answer_contract import build_structured_answer
from evaluation.qa_regression_fixture import CATEGORY_RULES, PRIMARY_CASES, SHADOW_FAILURE_CASES, QARegressionCase

DEFAULT_OUTPUT = Path("output/eval/qa_regression_report.json")


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _evaluate_primary(case: QARegressionCase) -> dict[str, Any]:
    answer = case.answer
    contract = build_structured_answer(answer, case.executed)
    checks: list[CheckResult] = []

    if case.case_id == "citation-missing-title-year":
        checks.extend([
            CheckResult("status remains supported", contract["status"] == "supported", str(contract["status"])),
            CheckResult(
                "citation gate fail-closed",
                contract["citation_compliance"] == "missing_required_citations",
                str(contract["citation_compliance"]),
            ),
            CheckResult(
                "answer mode downgraded",
                contract["answer_mode"] == "generative_non_evidentiary",
                str(contract["answer_mode"]),
            ),
        ])
    elif case.case_id == "citation-wrong-title-substring":
        checks.extend([
            CheckResult(
                "wrong title rejected",
                contract["citation_compliance"] == "missing_required_citations",
                str(contract["citation_compliance"]),
            ),
            CheckResult(
                "still treated as critical claim",
                contract["status"] == "supported",
                str(contract["status"]),
            ),
        ])
    elif case.case_id == "confirmation-bias-honest-abstention":
        checks.extend([
            CheckResult(
                "keeps evidence_insufficient status",
                contract["status"] == "evidence_insufficient",
                str(contract["status"]),
            ),
            CheckResult(
                "answer avoids overclaim",
                not _contains_any(answer[:80], ("明确支持", "已经证明", "强支持")),
                answer[:80],
            ),
            CheckResult(
                "rejection category preserved",
                contract["uncertainty"]["category"] == "evidence_insufficient",
                str(contract["uncertainty"]["category"]),
            ),
        ])
    elif case.case_id == "time-boundary-2026":
        checks.extend([
            CheckResult("status is not_found", contract["status"] == "not_found", str(contract["status"])),
            CheckResult("mentions 2026 boundary", "2026" in answer, answer),
            CheckResult(
                "does not claim 2027 evidence",
                "2027 年的论文已经证明" not in answer,
                answer,
            ),
        ])
    elif case.case_id == "correlation-not-causation":
        hints = tuple(contract["uncertainty"].get("qualification_hints") or [])
        checks.extend([
            CheckResult(
                "stays evidence_insufficient",
                contract["status"] == "evidence_insufficient",
                str(contract["status"]),
            ),
            CheckResult(
                "qualification hints preserved",
                "相关性不等于因果" in hints and "现有研究多为观察性研究" in hints,
                json.dumps(hints, ensure_ascii=False),
            ),
            CheckResult(
                "answer keeps correlation boundary",
                "不能直接证明因果" in answer or "不能证明因果" in answer,
                answer,
            ),
        ])
    elif case.case_id == "evidence-insufficient-vs-not-found":
        checks.extend([
            CheckResult(
                "not mistaken as not_found",
                contract["status"] == "evidence_insufficient",
                str(contract["status"]),
            ),
            CheckResult(
                "has calibrated rejection",
                bool(contract["uncertainty"]["calibrated_rejection"]),
                str(contract["uncertainty"]["calibrated_rejection"]),
            ),
            CheckResult(
                "citations still carried",
                bool(contract["citations"]),
                str(len(contract["citations"])),
            ),
        ])
    elif case.case_id == "dependency-failure-explicit":
        checks.extend([
            CheckResult(
                "dependency failure surfaced",
                contract["status"] == "dependency_failure",
                str(contract["status"]),
            ),
            CheckResult(
                "non evidentiary mode",
                contract["answer_mode"] == "generative_non_evidentiary",
                str(contract["answer_mode"]),
            ),
            CheckResult(
                "tool basis preserved",
                contract["tool_basis"] == ["verify_claim"],
                json.dumps(contract["tool_basis"], ensure_ascii=False),
            ),
        ])
    else:
        raise ValueError(f"Unhandled primary case: {case.case_id}")

    return {
        "case_id": case.case_id,
        "category": case.category,
        "question": case.question,
        "rule": case.rule,
        "expected_behavior": "pass_or_fail_closed",
        "passed": all(item.passed for item in checks),
        "checks": [item.__dict__ for item in checks],
        "contract": contract,
        "answer": answer,
    }


def _evaluate_shadow_failure(case: QARegressionCase) -> dict[str, Any]:
    answer = case.answer
    contract = build_structured_answer(answer, case.executed)
    checks: list[CheckResult] = []

    if case.case_id == "shadow-confirmation-bias-overclaim":
        checks.extend([
            CheckResult(
                "answer contains overclaim",
                _contains_any(answer[:80], ("明确支持", "已经明确支持", "已经证明", "是的")),
                answer[:80],
            ),
            CheckResult(
                "contract still says evidence_insufficient",
                contract["status"] == "evidence_insufficient",
                str(contract["status"]),
            ),
        ])
    elif case.case_id == "shadow-temporal-overclaim-2027":
        checks.extend([
            CheckResult(
                "answer falsely claims future evidence",
                "2027 年的论文已经证明" in answer,
                answer,
            ),
            CheckResult("contract says not_found", contract["status"] == "not_found", str(contract["status"])),
        ])
    elif case.case_id == "shadow-causality-overclaim":
        checks.extend([
            CheckResult("answer overclaims causality", "证明咖啡会因果性" in answer, answer),
            CheckResult(
                "contract remains evidence_insufficient",
                contract["status"] == "evidence_insufficient",
                str(contract["status"]),
            ),
        ])
    else:
        raise ValueError(f"Unhandled shadow case: {case.case_id}")

    detected = all(item.passed for item in checks)
    return {
        "case_id": case.case_id,
        "category": case.category,
        "question": case.question,
        "rule": case.rule,
        "expected_behavior": "must_be_flagged_as_bad_answer",
        "detected": detected,
        "checks": [item.__dict__ for item in checks],
        "contract": contract,
        "answer": answer,
    }


def _category_summary(primary_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in primary_results:
        grouped[item["category"]].append(item)

    summary = []
    for category, items in grouped.items():
        summary.append({
            "category": category,
            "samples": len(items),
            "passed": sum(1 for item in items if item["passed"]),
            "rule": CATEGORY_RULES[category],
        })
    return sorted(summary, key=lambda item: item["category"])


def _manual_review_rows(primary_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in primary_results:
        contract = item["contract"]
        rows.append({
            "case_id": item["case_id"],
            "category": item["category"],
            "question": item["question"],
            "answer": item["answer"],
            "expected_status": contract["status"],
            "expected_citation_compliance": contract["citation_compliance"],
            "manual_support_judgement": "",
            "manual_citation_precision": "",
            "manual_notes": "",
        })
    return rows


def _to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SciScope A03 科研问答回归与对抗集",
        "",
        f"生成时间：{report['generated_at']}",
        f"自动合同回归：**{report['primary_passed']}/{report['primary_total']}**",
        f"影子失败检测：**{report['shadow_detected']}/{report['shadow_total']}**",
        "",
        "## 1. 分类主表",
        "",
        "| 类别 | 样本数 | 通过 | 规则 |",
        "|---|---:|---:|---|",
    ]
    for item in report["category_summary"]:
        lines.append(f"| {item['category']} | {item['samples']} | {item['passed']} | {item['rule']} |")

    lines.extend([
        "",
        "## 2. 自动回归明细",
        "",
        "| case_id | 类别 | 结果 | 预期行为 |",
        "|---|---|---|---|",
    ])
    for item in report["primary_results"]:
        lines.append(
            f"| {item['case_id']} | {item['category']} | {'✅' if item['passed'] else '❌'} | {item['rule']} |"
        )

    lines.extend([
        "",
        "## 3. 影子失败例（应当被检测出来）",
        "",
        "| case_id | 类别 | 是否成功识别坏答案 |",
        "|---|---|---|",
    ])
    for item in report["shadow_results"]:
        lines.append(
            f"| {item['case_id']} | {item['category']} | {'✅' if item['detected'] else '❌'} |"
        )

    failed_primary = [item for item in report["primary_results"] if not item["passed"]]
    detected_shadow = [item for item in report["shadow_results"] if item["detected"]]
    lines.extend(["", "## 4. 失败例", ""])
    if not failed_primary and not detected_shadow:
        lines.append("- 当前没有自动失败例。")
    else:
        for item in failed_primary:
            lines.append(f"### 主集失败：{item['case_id']}")
            lines.append(f"- 规则：{item['rule']}")
            for check in item["checks"]:
                lines.append(f"- {'✅' if check['passed'] else '❌'} {check['name']}：{check['detail']}")
            lines.append("")
        for item in detected_shadow:
            lines.append(f"### 影子坏答案：{item['case_id']}")
            lines.append(f"- 规则：{item['rule']}")
            for check in item["checks"]:
                lines.append(f"- {'✅' if check['passed'] else '❌'} {check['name']}：{check['detail']}")
            lines.append("")

    lines.extend([
        "## 5. 人工复核边界",
        "",
        "- 自动部分只验证 `answer-contract/v1`、fail-closed 纪律、边界措辞与固定引文规则。",
        "- `manual_support_judgement` 与 `manual_citation_precision` 仍需人工填写；本脚本不输出伪造人工分数。",
        "",
        "---",
        "*复现：`rtk python3 -m evaluation.eval_qa_regression`（纯离线、冻结 fixture、不调用在线模型）。*",
    ])
    return "\n".join(lines)


def run(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    primary_results = [_evaluate_primary(case) for case in PRIMARY_CASES]
    shadow_results = [_evaluate_shadow_failure(case) for case in SHADOW_FAILURE_CASES]
    manual_rows = _manual_review_rows(primary_results)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_total": len(primary_results),
        "primary_passed": sum(1 for item in primary_results if item["passed"]),
        "shadow_total": len(shadow_results),
        "shadow_detected": sum(1 for item in shadow_results if item["detected"]),
        "category_summary": _category_summary(primary_results),
        "primary_results": primary_results,
        "shadow_results": shadow_results,
        "manual_review_template_fields": [
            "case_id",
            "category",
            "question",
            "answer",
            "expected_status",
            "expected_citation_compliance",
            "manual_support_judgement",
            "manual_citation_precision",
            "manual_notes",
        ],
        "manual_review_rows": manual_rows,
        "sample_counts": dict(Counter(item["category"] for item in primary_results)),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path.with_suffix(".md").write_text(_to_markdown(report), encoding="utf-8")
    manual_template = output_path.parent / "qa_regression_manual_review_template.jsonl"
    manual_template.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in manual_rows) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline QA regression over frozen SciScope fixtures.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to output JSON report.")
    args = parser.parse_args()
    report = run(output_path=args.output)
    print(
        json.dumps(
            {
                "primary_passed": report["primary_passed"],
                "primary_total": report["primary_total"],
                "shadow_detected": report["shadow_detected"],
                "shadow_total": report["shadow_total"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
