"""A02 answer contract: unified final meta/aggregate contract over tool results."""

from __future__ import annotations

import json

from backend.app.agent import langgraph_runtime
from backend.app.agent.answer_contract import build_structured_answer
from backend.app.agent.events import event_parts, summarize_events


def _verify_claim_payload(
    verdict: str,
    *,
    reason: str = "",
    mode: str = "stance",
    citations: list[dict] | None = None,
) -> str:
    citations = citations if citations is not None else [
        {
            "paper_id": "W1",
            "标题": "Coffee study",
            "年份": 2023,
            "chunk_uid": "c" * 40,
            "source_field": "full_text",
            "证据句": "Coffee intake was associated with lower cardiovascular risk.",
            "立场": "SUPPORT" if verdict != "证据反驳" else "CONTRADICT",
            "置信度": 0.95,
        }
    ]
    payload = {
        "论断": "咖啡能降低心脏病风险",
        "支持等级": verdict,
        "判定方式": mode,
        "证据": citations,
    }
    if reason:
        key = "理由" if "未检索到相关文献" in reason else "拒答原因"
        payload[key] = reason
    return json.dumps(payload, ensure_ascii=False)


def test_answer_contract_distinguishes_not_found() -> None:
    contract = build_structured_answer(
        "当前语料中未找到直接证据。",
        {"verify_claim|{}": _verify_claim_payload("证据不足", reason="未检索到相关文献。", citations=[])},
    )
    assert contract["status"] == "not_found"
    assert contract["uncertainty"]["category"] == "not_found"


def test_answer_contract_distinguishes_evidence_insufficient() -> None:
    contract = build_structured_answer(
        "现有文献证据不足，不能直接下结论。",
        {"verify_claim|{}": _verify_claim_payload("证据不足", reason="有 1 条证据判定置信度低于阈值 0.5,拒绝强判为支持/反驳。")},
    )
    assert contract["status"] == "evidence_insufficient"
    assert contract["uncertainty"]["category"] == "evidence_insufficient"


def test_answer_contract_distinguishes_abstained_similarity_fallback() -> None:
    contract = build_structured_answer(
        "当前只能说明相关，不能确认支持。",
        {
            "verify_claim|{}": _verify_claim_payload(
                "证据不足",
                reason="当前仅能给出相关度，无法确认文献立场。",
                mode="similarity",
            )
        },
    )
    assert contract["status"] == "abstained"
    assert contract["uncertainty"]["category"] == "abstained"


def test_answer_contract_marks_dependency_failure() -> None:
    contract = build_structured_answer(
        "当前无法完成核查。",
        {"verify_claim|{}": "工具 verify_claim 执行出错: RuntimeError: db down"},
    )
    assert contract["status"] == "dependency_failure"
    assert contract["answer_mode"] == "generative_non_evidentiary"
    assert contract["uncertainty"]["category"] == "dependency_failure"


def test_answer_contract_marks_critical_answer_without_citations_as_generative() -> None:
    contract = build_structured_answer(
        "结论是该说法有较强支持。",
        {"verify_claim|{}": _verify_claim_payload("强支持")},
    )
    assert contract["status"] == "supported"
    assert contract["citation_compliance"] == "missing_required_citations"
    assert contract["answer_mode"] == "generative_non_evidentiary"


def test_answer_contract_accepts_multiple_title_year_citation_formats() -> None:
    executed = {"verify_claim|{}": _verify_claim_payload("强支持")}
    assert build_structured_answer("《Coffee study》(2023) 支持该结论。", executed)["citation_compliance"] == "ok"
    assert build_structured_answer("Coffee study (2023) 支持该结论。", executed)["citation_compliance"] == "ok"
    assert build_structured_answer("Coffee study（2023）支持该结论。", executed)["citation_compliance"] == "ok"
    assert build_structured_answer("Coffee study, 2023 支持该结论。", executed)["citation_compliance"] == "ok"
    assert build_structured_answer("Coffee study，2023 支持该结论。", executed)["citation_compliance"] == "ok"


def test_answer_contract_citation_gate_avoids_title_substring_false_positive() -> None:
    executed = {
        "verify_claim|{}": _verify_claim_payload(
            "强支持",
            citations=[{"paper_id": "W1", "标题": "Coffee", "年份": 2023, "chunk_uid": "c" * 40, "source_field": "full_text", "证据句": "", "立场": "SUPPORT", "置信度": 0.95}],
        )
    }
    contract = build_structured_answer("Coffee study (2023) 支持该结论。", executed)
    assert contract["citation_compliance"] == "missing_required_citations"


def test_answer_contract_recovers_from_malformed_embedded_structured_answer() -> None:
    payload = json.loads(_verify_claim_payload("证据反驳"))
    payload["structured_answer"] = {"status": 123, "citations": "bad-shape"}
    contract = build_structured_answer(
        "《Coffee study》(2023) 与原论断相反。",
        {"verify_claim|{}": json.dumps(payload, ensure_ascii=False)},
    )
    assert contract["status"] == "contradicted"
    assert contract["citation_compliance"] == "ok"


def test_answer_contract_fail_closed_when_embedded_and_payload_are_both_malformed() -> None:
    payload = {
        "structured_answer": {"status": 123, "citations": "bad-shape"},
        "证据": "bad-shape",
    }
    contract = build_structured_answer(
        "当前无法完成核查。",
        {"verify_claim|{}": json.dumps(payload, ensure_ascii=False)},
    )
    assert contract["status"] == "dependency_failure"
    assert contract["uncertainty"]["category"] == "dependency_failure"


def test_final_event_meta_and_aggregate_carry_structured_answer() -> None:
    answer = "现有证据更支持相反方向。《Coffee study》(2023) 与原论断相反。"
    executed = {"verify_claim|{}": _verify_claim_payload("证据反驳")}
    meta = langgraph_runtime._final_meta(  # type: ignore[attr-defined]
        {"executed": executed, "tokens_in": 0, "tokens_out": 0},
        answer,
        "completed",
    )
    events = [
        ("tool_call", {"name": "verify_claim", "args": {"claim": "咖啡能降低心脏病风险"}}),
        ("final", answer, meta),
    ]

    final_kind, final_payload, final_meta = event_parts(events[-1])
    result = summarize_events(events)

    assert final_kind == "final"
    assert "Coffee study" in final_payload
    assert final_meta["structured_answer"]["status"] == "contradicted"
    assert final_meta["structured_answer"]["citation_compliance"] == "ok"
    assert final_meta["structured_answer"]["citations"][0]["chunk_uid"] == "c" * 40
    assert result["structured_answer"]["status"] == "contradicted"
    assert result["structured_answer"]["citation_compliance"] == "ok"
