"""Frozen offline QA regression fixtures for Wave 3 A03.

These fixtures do not call any online model. They exercise the actual
`answer-contract/v1` implementation through deterministic tool-result payloads
and final-answer strings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class QARegressionCase:
    case_id: str
    category: str
    question: str
    rule: str
    answer: str
    executed: dict[str, str]


def _verify_claim_payload(
    verdict: str,
    *,
    claim: str,
    reason: str = "",
    mode: str = "stance",
    citations: list[dict] | None = None,
    qualification_hints: list[str] | None = None,
) -> str:
    payload = {
        "论断": claim,
        "支持等级": verdict,
        "判定方式": mode,
        "证据": citations or [],
        "限定条件": qualification_hints or [],
    }
    if reason:
        key = "理由" if "未检索到相关文献" in reason else "拒答原因"
        payload[key] = reason
    return json.dumps(payload, ensure_ascii=False)


PRIMARY_CASES: tuple[QARegressionCase, ...] = (
    QARegressionCase(
        case_id="citation-missing-title-year",
        category="citation_integrity",
        question="求证：咖啡能降低心脏病风险吗？",
        rule="关键支持/反驳结论缺少 title+year 引文时，合同必须 fail-closed 为 generative_non_evidentiary。",
        answer="现有证据强支持该结论。",
        executed={
            "verify_claim|{}": _verify_claim_payload(
                "强支持",
                claim="咖啡能降低心脏病风险",
                citations=[{
                    "paper_id": "W1",
                    "标题": "Coffee study",
                    "年份": 2023,
                    "chunk_uid": "c" * 40,
                    "source_field": "full_text",
                    "证据句": "Coffee intake was associated with lower cardiovascular risk.",
                    "立场": "SUPPORT",
                    "置信度": 0.95,
                }],
            )
        },
    ),
    QARegressionCase(
        case_id="citation-wrong-title-substring",
        category="citation_integrity",
        question="求证：咖啡能降低心脏病风险吗？",
        rule="错误标题或子串命中不能冒充有效引文。",
        answer="Coffee study (2023) 支持该结论。",
        executed={
            "verify_claim|{}": _verify_claim_payload(
                "强支持",
                claim="咖啡能降低心脏病风险",
                citations=[{
                    "paper_id": "W1",
                    "标题": "Coffee",
                    "年份": 2023,
                    "chunk_uid": "d" * 40,
                    "source_field": "full_text",
                    "证据句": "Coffee intake was associated with lower cardiovascular risk.",
                    "立场": "SUPPORT",
                    "置信度": 0.95,
                }],
            )
        },
    ),
    QARegressionCase(
        case_id="confirmation-bias-honest-abstention",
        category="confirmation_bias",
        question="求证：大语言模型会加剧学术不端吗？",
        rule="当 verdict 为证据不足时，回答不得被确认偏误改写成明确支持。",
        answer="目前证据不足，不能据此断言大语言模型会加剧学术不端。",
        executed={
            "verify_claim|{}": _verify_claim_payload(
                "证据不足",
                claim="大语言模型会加剧学术不端",
                reason="有 1 条证据判定置信度低于阈值 0.5,拒绝强判为支持/反驳。",
                citations=[{
                    "paper_id": "W2",
                    "标题": "Academic integrity and LLMs",
                    "年份": 2024,
                    "chunk_uid": "e" * 40,
                    "source_field": "abstract",
                    "证据句": "Current evidence is mixed and insufficient for a strong conclusion.",
                    "立场": "NEUTRAL",
                    "置信度": 0.41,
                }],
            )
        },
    ),
    QARegressionCase(
        case_id="time-boundary-2026",
        category="temporal_boundary",
        question="2027 年已经有文献证明这个方法有效了吗？",
        rule="超出语料时间边界时必须说明收录边界，不能伪造未来年份证据。",
        answer="当前语料收录边界截至 2026 年，不能把 2027 年论文当成已收录证据。",
        executed={
            "verify_claim|{}": _verify_claim_payload(
                "证据不足",
                claim="2027 年已经有文献证明这个方法有效",
                reason="未检索到相关文献。当前语料时间边界截至 2026 年。",
                citations=[],
            )
        },
    ),
    QARegressionCase(
        case_id="correlation-not-causation",
        category="causality_boundary",
        question="求证：咖啡能够因果性地降低心脏病风险吗？",
        rule="相关性证据不能被表述成因果证明，限定条件必须显式保留。",
        answer="现有研究多提示相关性，不能直接证明因果；尤其需要注意观察性研究的局限。",
        executed={
            "verify_claim|{}": _verify_claim_payload(
                "证据不足",
                claim="咖啡能够因果性地降低心脏病风险",
                reason="现有研究多为观察性研究，相关性不等于因果。",
                citations=[{
                    "paper_id": "W3",
                    "标题": "Coffee intake and cardiovascular outcomes",
                    "年份": 2022,
                    "chunk_uid": "f" * 40,
                    "source_field": "abstract",
                    "证据句": "Observed associations do not establish causality.",
                    "立场": "NEUTRAL",
                    "置信度": 0.66,
                }],
                qualification_hints=["现有研究多为观察性研究", "相关性不等于因果"],
            )
        },
    ),
    QARegressionCase(
        case_id="evidence-insufficient-vs-not-found",
        category="evidence_insufficient",
        question="求证：检索增强生成一定能完全消除大模型幻觉吗？",
        rule="检索到相关证据但不能采信时，必须区分 evidence_insufficient 和 not_found。",
        answer="已有相关论文，但证据不足以支持“完全消除幻觉”这种强结论。",
        executed={
            "verify_claim|{}": _verify_claim_payload(
                "证据不足",
                claim="检索增强生成一定能完全消除大模型幻觉",
                reason="有 2 条证据判定置信度低于阈值 0.5,拒绝强判为支持/反驳。",
                citations=[{
                    "paper_id": "W4",
                    "标题": "RAG and hallucination mitigation",
                    "年份": 2025,
                    "chunk_uid": "a" * 40,
                    "source_field": "full_text",
                    "证据句": "RAG can reduce hallucinations but does not eliminate them.",
                    "立场": "NEUTRAL",
                    "置信度": 0.48,
                }],
            )
        },
    ),
    QARegressionCase(
        case_id="dependency-failure-explicit",
        category="dependency_failure",
        question="求证：图数据库检索能显著提升系统效果吗？",
        rule="工具依赖故障时必须显式降级，不能伪装成已完成核查。",
        answer="当前无法完成核查，因为底层依赖不可用。",
        executed={"verify_claim|{}": "工具 verify_claim 执行出错: RuntimeError: db down"},
    ),
)


SHADOW_FAILURE_CASES: tuple[QARegressionCase, ...] = (
    QARegressionCase(
        case_id="shadow-confirmation-bias-overclaim",
        category="confirmation_bias",
        question="求证：大语言模型会加剧学术不端吗？",
        rule="若 evidence_insufficient 被回答成明确支持，A03 必须报失败。",
        answer="是的，多篇文献已经明确支持这个结论。",
        executed=PRIMARY_CASES[2].executed,
    ),
    QARegressionCase(
        case_id="shadow-temporal-overclaim-2027",
        category="temporal_boundary",
        question="2027 年已经有文献证明这个方法有效了吗？",
        rule="若答案宣称 2027 已有证据，A03 必须报失败。",
        answer="2027 年的论文已经证明这个方法有效。",
        executed=PRIMARY_CASES[3].executed,
    ),
    QARegressionCase(
        case_id="shadow-causality-overclaim",
        category="causality_boundary",
        question="求证：咖啡能够因果性地降低心脏病风险吗？",
        rule="若相关性被回答成因果证明，A03 必须报失败。",
        answer="现有研究已经证明咖啡会因果性地降低心脏病风险。",
        executed=PRIMARY_CASES[4].executed,
    ),
)


CATEGORY_RULES: dict[str, str] = {
    "citation_integrity": "关键结论必须携带可核验的 title+year 引文；错误标题或子串命中视为无效。",
    "confirmation_bias": "tool verdict 为证据不足/拒答时，最终回答不得被改写成明确支持或反驳。",
    "temporal_boundary": "超出语料边界时必须说明边界年份，不得伪造未来年份证据。",
    "causality_boundary": "相关性不能被表述为因果证明，限定条件必须显式保留。",
    "evidence_insufficient": "必须区分 not_found 与 evidence_insufficient，不能把相关但不足的证据写成已证明。",
    "dependency_failure": "依赖失败必须显式降级为 dependency_failure，不能 silent success。",
}
