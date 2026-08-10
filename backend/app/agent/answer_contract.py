"""Shared answer/citation/uncertainty contract for agent-facing answers.

This module keeps the final answer payload compatible with the current TUI
(`final` payload remains a plain string) while adding a structured envelope that
API callers and future UIs can consume deterministically from final-event meta
or the aggregated `/api/agent` response.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.app.agent.tool_runner import MISSING_RESULT_NOTE
from backend.app.models.schemas import AnswerCitation, AnswerUncertainty, StructuredAnswer
from pydantic import ValidationError

_CRITICAL_STATUSES = {
    "supported",
    "partially_supported",
    "contradicted",
    "disputed",
}
_EVIDENCE_TOOLS = {
    "search_literature",
    "summarize_field",
    "get_paper",
    "paper_structured",
    "verify_claim",
}


def _tool_name(signature: str) -> str:
    return str(signature).split("|", 1)[0].strip()


def _citation_seen_in_answer(answer: str, citation: dict[str, Any]) -> bool:
    title = str(citation.get("title") or "").strip()
    year = citation.get("year")
    if not title or year in (None, ""):
        return False
    year_text = str(year).strip()
    escaped_title = re.escape(title)
    patterns = (
        rf"《{escaped_title}》\s*[（(]\s*{re.escape(year_text)}\s*[）)]",
        rf"(?<![\w\u4e00-\u9fff]){escaped_title}(?![\w\u4e00-\u9fff])\s*[（(]\s*{re.escape(year_text)}\s*[）)]",
        rf"(?<![\w\u4e00-\u9fff]){escaped_title}(?![\w\u4e00-\u9fff])\s*[,，]\s*{re.escape(year_text)}(?!\d)",
    )
    return any(re.search(pattern, answer) for pattern in patterns)


def _dependency_failure(tool_name: str, result: str) -> StructuredAnswer:
    message = result.strip() or "tool execution failed"
    return StructuredAnswer(
        capability="general_research_answer",
        status="dependency_failure",
        answer_mode="generative_non_evidentiary",
        citation_compliance="not_applicable",
        tool_basis=[tool_name],
        uncertainty=AnswerUncertainty(category="dependency_failure", message=message),
    )


def _generic_contract(tool_names: list[str]) -> StructuredAnswer:
    return StructuredAnswer(
        capability="general_research_answer",
        status="not_applicable",
        answer_mode="generative_non_evidentiary",
        citation_compliance="not_applicable",
        tool_basis=tool_names,
    )


def _claim_contract_from_tool(payload: dict[str, Any], tool_name: str) -> StructuredAnswer:
    verdict = str(payload.get("支持等级") or "").strip()
    reason = str(payload.get("拒答原因") or payload.get("理由") or "").strip()
    status = {
        "强支持": "supported",
        "部分支持": "partially_supported",
        "证据反驳": "contradicted",
        "存在争议": "disputed",
        "证据不足": "evidence_insufficient",
    }.get(verdict, "not_applicable")
    if status == "evidence_insufficient" and "未检索到相关文献" in str(payload.get("理由") or ""):
        status = "not_found"
    if str(payload.get("判定方式") or "").strip().lower() == "similarity":
        status = "abstained"

    citations: list[AnswerCitation] = []
    for row in payload.get("证据") or []:
        if not isinstance(row, dict):
            continue
        citations.append(
            AnswerCitation(
                paper_id=str(row.get("paper_id") or "") or None,
                title=str(row.get("标题") or ""),
                year=row.get("年份"),
                chunk_uid=str(row.get("chunk_uid") or "") or None,
                source_field=str(row.get("source_field") or "") or None,
                evidence_sentence=str(row.get("证据句") or ""),
                stance=row.get("立场"),
                confidence=row.get("置信度"),
            )
        )

    qualification_hints = []
    raw_hints = payload.get("限定条件") or []
    if isinstance(raw_hints, list):
        qualification_hints = [str(item) for item in raw_hints if str(item).strip()]

    uncertainty = AnswerUncertainty(
        category={
            "not_found": "not_found",
            "evidence_insufficient": "evidence_insufficient",
            "abstained": "abstained",
        }.get(status, "none"),
        message=reason,
        calibrated_rejection=status in {"evidence_insufficient", "abstained", "not_found"},
        qualification_hints=qualification_hints,
    )
    return StructuredAnswer(
        capability="claim_verification",
        status=status,
        verdict_label=verdict,
        answer_mode="evidence_based",
        citation_compliance="not_applicable",
        citations=citations,
        uncertainty=uncertainty,
        tool_basis=[tool_name],
        claim=str(payload.get("论断") or "") or None,
    )


def _parse_tool_result(tool_name: str, result: str) -> StructuredAnswer | None:
    stripped = (result or "").strip()
    if not stripped:
        return None
    if stripped == MISSING_RESULT_NOTE or stripped.startswith("工具 ") or stripped.startswith("[未授权]") or stripped.startswith("[未执行]"):
        return _dependency_failure(tool_name, stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if tool_name == "verify_claim" and isinstance(payload, dict):
        embedded = payload.get("structured_answer")
        if isinstance(embedded, dict):
            try:
                return StructuredAnswer.model_validate(embedded)
            except ValidationError:
                try:
                    rebuilt = _claim_contract_from_tool(payload, tool_name)
                    if rebuilt.status == "not_applicable":
                        return _dependency_failure(tool_name, "malformed embedded structured_answer")
                    return rebuilt
                except Exception:
                    return _dependency_failure(tool_name, "malformed embedded structured_answer")
        return _claim_contract_from_tool(payload, tool_name)
    return None


def _apply_citation_gate(contract: StructuredAnswer, answer: str) -> StructuredAnswer:
    if contract.status not in _CRITICAL_STATUSES:
        return contract.model_copy(update={"citation_compliance": "not_applicable"})
    citations = [item.model_dump() for item in contract.citations]
    seen = any(_citation_seen_in_answer(answer, citation) for citation in citations)
    if seen:
        return contract.model_copy(update={"citation_compliance": "ok"})
    message = "Final answer omitted required title+year citations for a critical evidence claim."
    uncertainty = contract.uncertainty.model_copy(
        update={"category": "generative_non_evidentiary", "message": message}
    )
    return contract.model_copy(
        update={
            "answer_mode": "generative_non_evidentiary",
            "citation_compliance": "missing_required_citations",
            "uncertainty": uncertainty,
        }
    )


def build_structured_answer(answer: str, executed: dict[str, str] | None) -> dict[str, Any]:
    """Derive one shared answer contract from executed tool results."""
    executed = executed or {}
    tool_names = [_tool_name(signature) for signature in executed]
    contract: StructuredAnswer | None = None
    for signature, result in executed.items():
        tool_name = _tool_name(signature)
        parsed = _parse_tool_result(tool_name, result)
        if parsed is None:
            continue
        contract = parsed
        if parsed.capability == "claim_verification":
            break
    if contract is None:
        contract = _generic_contract(tool_names)
    contract = _apply_citation_gate(contract, answer)
    if not contract.tool_basis:
        contract = contract.model_copy(update={"tool_basis": tool_names})
    return contract.model_dump()
