"""Offline tests for the dialogue-eval harness's check logic (no LLM needed)."""

from __future__ import annotations

from evaluation.eval_dialogue import CASES, TurnRecord, _cites_papers, _no_narration


def _case(case_id: str):
    return next(c for c in CASES if c.case_id == case_id)


def _check(case, name):
    return dict((n, p) for n, p in case.checks)[name]


def test_narration_check_flags_leading_transition_only():
    assert _no_narration(TurnRecord(question="q", final="RAG 领域正在快速发展……")) is True
    assert _no_narration(TurnRecord(question="q", final="好的,数据已全部返回。下面综合作答。\n---\n正文")) is False
    # Deep in the body (quoting, not narrating) is fine.
    assert _no_narration(TurnRecord(question="q", final="正文" * 100 + "现在综合")) is True


def test_citation_check_needs_title_and_year():
    assert _cites_papers(TurnRecord(question="q", final="《HopRAG》(2025) 提出了段落图。")) is True
    assert _cites_papers(TurnRecord(question="q", final="有很多论文讨论了这个问题。")) is False


def test_reference_case_rejects_fabricated_ordinal_id():
    check = _check(_case("reference-resolution"), "不编造序号 paper_id")
    bad = TurnRecord(question="q", tool_calls=[{"name": "get_paper", "args": {"paper_id": "2"}}])
    good = TurnRecord(question="q", tool_calls=[{"name": "get_paper", "args": {"paper_id": "W4412888702"}}])
    assert check(bad) is False
    assert check(good) is True


def test_claim_case_catches_verdict_flip():
    check = _check(_case("claim-honesty"), "verdict 与回答方向一致")
    flipped = TurnRecord(
        question="q",
        final="**是的,多篇文献明确支持这一论断。**",
        tool_results=[{"name": "verify_claim", "result": '{"支持等级": "证据不足"}'}],
    )
    honest = TurnRecord(
        question="q",
        final="目前文献库中的证据不足以支持该论断。",
        tool_results=[{"name": "verify_claim", "result": '{"支持等级": "证据不足"}'}],
    )
    assert check(flipped) is False
    assert check(honest) is True


def test_trend_case_catches_direction_misread():
    check = _check(_case("trend-faithful"), "不显著趋势不说成显著上升")
    misread = TurnRecord(
        question="q",
        final="该领域呈显著上升趋势。",
        tool_results=[{"name": "get_trends", "result": '[{"增长方向": "falling(下降)", "趋势显著性": "不显著(p=1.00)"}]'}],
    )
    faithful = TurnRecord(
        question="q",
        final="趋势统计不显著,已进入成熟期。",
        tool_results=[{"name": "get_trends", "result": '[{"增长方向": "falling(下降)", "趋势显著性": "不显著(p=1.00)"}]'}],
    )
    assert check(misread) is False
    assert check(faithful) is True


def test_every_case_has_checks_and_pinned_reason():
    for case in CASES:
        assert case.checks, f"{case.case_id} has no checks"
        assert case.pinned_from, f"{case.case_id} missing pinned_from rationale"
