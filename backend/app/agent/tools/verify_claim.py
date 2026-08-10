"""verify_claim — fact-check a claim via retrieval + L3 stance judgement.

Pipeline (国赛 WB2, judge version l3-1):

1. Retrieve topically-relevant evidence via hybrid search.
2. Judge each evidence with the L3 judge (`services/stance/judge.py`): stance
   (SUPPORT / CONTRADICT / NEUTRAL), self-reported confidence, the verbatim
   evidence sentence, and qualifier-mismatch hints (population/dose/time/
   species/target).
3. Calibrate: only stances above `SCISCOPE_STANCE_MIN_CONFIDENCE` count; low
   confidence or qualifier-mismatched evidence cannot drive a confident verdict
   — the tool prefers 证据不足 (rejection) over a confident guess.
4. Aggregate to 强支持 / 部分支持 / 存在争议 / 证据反驳 / 证据不足 and persist
   judged evidence to `claim_evidence_stance` (矛盾即资产).

Fallback discipline: when the LLM judge is unavailable (offline / mock mode),
the similarity-only path may ONLY conclude 证据不足 — similarity measures
relatedness, not entailment, so it must never emit 强支持/部分支持.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Iterator

from backend.app.agent.tools import base
from backend.app.agent.tools.base import Tool
from backend.app.services.stance import judge as stance_judge

SCHEMA = {
    "type": "function",
    "function": {
        "name": "verify_claim",
        "description": (
            "核查一句论断是否有文献证据支持:先检索相关文献,再用大模型逐条判定证据对论断的"
            "「立场」(支持/反驳/中立)并给出置信度与证据原句,返回支持等级(强支持/部分支持/"
            "存在争议/证据反驳/证据不足)。能区分一句论断与它的反面;置信不足或证据限定条件"
            "不匹配时如实返回「证据不足」,不强行断言。用于'这个说法对吗/有没有依据/求证 X'"
            "类问题,或在你给出关键论断前自我核验。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim": {"type": "string", "description": "需要核查的一句论断,中英文均可"},
                "persist": {
                    "type": "boolean",
                    "description": "仅在受控环境中明确请求将已采信立场写入争议资产；默认 false。",
                    "default": False,
                },
            },
            "required": ["claim"],
        },
    },
}

# Minimum judge confidence for a stance to count toward a confident verdict.
_MIN_CONFIDENCE = float(os.getenv("SCISCOPE_STANCE_MIN_CONFIDENCE", "0.5"))
# Confidence at which a supporting evidence set warrants 强支持.
_STRONG_CONFIDENCE = 0.9


def _judge_stances(claim: str, evidence_texts: list[str]) -> stance_judge.JudgeResult:
    """L3 judge entry (kept at module level so tests can patch it)."""
    return stance_judge.judge_evidence(claim, evidence_texts)


def _structured_answer(
    *,
    claim: str,
    verdict: str,
    evidence: list[dict[str, Any]],
    reason: str = "",
    judgement_mode: str = "stance",
    qualification_hints: list[str] | None = None,
) -> dict[str, Any]:
    status = {
        "强支持": "supported",
        "部分支持": "partially_supported",
        "证据反驳": "contradicted",
        "存在争议": "disputed",
        "证据不足": "evidence_insufficient",
    }.get(verdict, "not_applicable")
    if verdict == "证据不足" and "未检索到相关文献" in reason:
        status = "not_found"
    if judgement_mode == "similarity":
        status = "abstained"
    return {
        "schema_version": "answer-contract/v1",
        "capability": "claim_verification",
        "status": status,
        "verdict_label": verdict,
        "answer_mode": "evidence_based",
        "citation_compliance": "not_applicable",
        "claim": claim,
        "tool_basis": ["verify_claim"],
        "citations": [
            {
                "paper_id": item.get("paper_id"),
                "title": item.get("标题") or "",
                "year": item.get("年份"),
                "chunk_uid": item.get("chunk_uid"),
                "source_field": item.get("source_field"),
                "evidence_sentence": item.get("证据句") or "",
                "stance": item.get("立场"),
                "confidence": item.get("置信度"),
            }
            for item in evidence
            if isinstance(item, dict)
        ],
        "uncertainty": {
            "category": {
                "not_found": "not_found",
                "evidence_insufficient": "evidence_insufficient",
                "abstained": "abstained",
            }.get(status, "none"),
            "message": reason,
            "calibrated_rejection": status in {"not_found", "evidence_insufficient", "abstained"},
            "qualification_hints": qualification_hints or [],
        },
    }


def _check_persist_permission(args: dict[str, Any]) -> str | None:
    """Allow ordinary verification, but gate the optional stance-asset write."""
    if args.get("persist") and not base.ALLOW_WRITE_TOOLS:
        return "verify_claim 请求写入 stance 资产，但当前为只读模式，未授权执行。"
    return None


def run(args: dict[str, Any]) -> Iterator[str]:
    """Generator handler: streams retrieve→score→judge→calibrate, returns the verdict."""
    from backend.app.core.config import get_settings
    from backend.app.services import retrieval_service
    from src.models.embeddings import get_embedder

    claim = str(args.get("claim") or "").strip()
    persist = bool(args.get("persist"))
    if not claim:
        return "verify_claim: claim 为空"

    yield "检索相关文献中…"
    results = retrieval_service.search(claim, limit=6)
    if not results:
        return json.dumps(
            {
                "论断": claim,
                "支持等级": "证据不足",
                "理由": "未检索到相关文献。",
                "证据": [],
                "structured_answer": _structured_answer(
                    claim=claim,
                    verdict="证据不足",
                    evidence=[],
                    reason="未检索到相关文献。",
                ),
            },
            ensure_ascii=False,
        )

    # Evidence texts (title + snippet) + metadata, in retrieval order.
    evid_texts, evid_meta = [], []
    for r in results:
        snippet = (r.snippet or "").strip()
        title = (r.title or "").strip()
        evid_texts.append(f"{title}. {snippet}"[:512])
        evid_meta.append(
            {
                "paper_id": r.paper_id,
                "标题": title,
                "年份": r.year,
                "chunk_uid": getattr(r, "chunk_uid", None),
                "source_field": getattr(r, "source_field", None),
            }
        )

    yield "计算跨语言接地相似度中…"
    embedder = get_embedder(get_settings().embedding_model)
    qv = embedder.encode_query(claim)
    pv = embedder.encode_passages(evid_texts)
    sims = [float(sum(a * b for a, b in zip(qv, row))) for row in pv]  # vectors are L2-normalized

    # Rank evidence by grounding similarity; keep texts aligned for the judge.
    ranked = sorted(zip(sims, evid_meta, evid_texts), key=lambda x: x[0], reverse=True)
    top_sim = ranked[0][0]
    ordered_texts = [text for _, _, text in ranked]

    yield "判定证据立场(L3)…"
    result = _judge_stances(claim, ordered_texts)

    if not result.ok:
        # Fallback discipline: similarity can only conclude 证据不足.
        note = (result.note or "").strip()
        reason_detail = (
            f"LLM 立场判定输出格式异常({note}),按纪律不采用其中任何立场。"
            if note
            else "LLM 立场判定不可用,按回退纪律只报证据不足,不做支持/反驳断言。"
        )
        return json.dumps(
            {
                "论断": claim,
                "支持等级": "证据不足",
                "判定方式": "similarity",
                "判定版本": "similarity",
                "最高接地相似度": round(top_sim, 3),
                "拒答原因": (
                    "当前仅能给出相关度(相似度=%.3f),无法确认文献立场;相似度衡量「相关」而非「支持」。"
                    "%s"
                )
                % (top_sim, reason_detail),
                "证据": [
                    {
                        **meta,
                        "接地相似度": round(sim, 3),
                        "立场": "NEUTRAL",
                        "判定方式": "similarity",
                        "chunk_uid": meta.get("chunk_uid"),
                        "source_field": meta.get("source_field"),
                    }
                    for sim, meta, _text in ranked[:4]
                ],
                "提示": "请如实表述:当前结论仅基于相关性,未获得立场判定。",
                "structured_answer": _structured_answer(
                    claim=claim,
                    verdict="证据不足",
                    evidence=[
                        {
                            **meta,
                            "接地相似度": round(sim, 3),
                            "立场": "NEUTRAL",
                            "判定方式": "similarity",
                            "chunk_uid": meta.get("chunk_uid"),
                            "source_field": meta.get("source_field"),
                        }
                        for sim, meta, _text in ranked[:4]
                    ],
                    reason=(
                        "当前仅能给出相关度(相似度=%.3f),无法确认文献立场;相似度衡量「相关」而非「支持」。%s"
                    )
                    % (top_sim, reason_detail),
                    judgement_mode="similarity",
                ),
            },
            ensure_ascii=False,
        )

    judgements = stance_judge.validate_evidence_sentences(result.judgements, ordered_texts)
    evidence = []
    for i, (sim, meta, _text) in enumerate(ranked):
        j = judgements[i]
        evidence.append(
            {
                **meta,
                "接地相似度": round(sim, 3),
                "立场": j.stance,
                "置信度": round(j.confidence, 2),
                "证据句": j.sentence,
                "限定条件": j.qualification,
                "chunk_uid": meta.get("chunk_uid"),
                "source_field": meta.get("source_field"),
            }
        )

    # Calibrated aggregation: confidence threshold + qualifier mismatch.
    # Non-finite confidence (NaN/±Infinity) is never countable: it must not
    # drive 强支持/部分支持/证据反驳 even if a judge layer ever leaked it.
    def countable(j: stance_judge.EvidenceJudgement) -> bool:
        return math.isfinite(j.confidence) and j.confidence >= _MIN_CONFIDENCE and not j.qualification

    support = [j for j in judgements if countable(j) and j.stance == "SUPPORT"]
    contradict = [j for j in judgements if countable(j) and j.stance == "CONTRADICT"]
    low_confidence = [j for j in judgements if j.stance != "NEUTRAL" and j.confidence < _MIN_CONFIDENCE]
    qualified = [j for j in judgements if j.stance != "NEUTRAL" and j.qualification]

    reject_reason = None
    if support and contradict:
        verdict = "存在争议"
    elif contradict:
        verdict = "证据反驳"
    elif support:
        verdict = "强支持" if max(j.confidence for j in support) >= _STRONG_CONFIDENCE else "部分支持"
    else:
        verdict = "证据不足"
        if low_confidence:
            reject_reason = (
                f"有 {len(low_confidence)} 条证据判定置信度低于阈值 {_MIN_CONFIDENCE:.1f},"
                "拒绝强判为支持/反驳。"
            )
        elif qualified:
            reject_reason = "证据存在限定条件不匹配(如人群/物种/剂量/时间),不能按一般性论断采信。"
        else:
            reject_reason = "未检索到明确支持或反驳的证据。"

    stats = {
        "支持": sum(1 for j in judgements if j.stance == "SUPPORT"),
        "反驳": sum(1 for j in judgements if j.stance == "CONTRADICT"),
        "中立": sum(1 for j in judgements if j.stance == "NEUTRAL"),
    }

    payload: dict[str, Any] = {
        "论断": claim,
        "支持等级": verdict,
        "判定方式": "stance",
        "判定版本": stance_judge.JUDGE_VERSION,
        "最高接地相似度": round(top_sim, 3),
        "证据": evidence[:4],
        "证据立场统计": stats,
        "提示": (
            "请据证据如实表述:'证据反驳'表示文献与论断相反,不要断言论断成立;"
            "'存在争议'表示文献有分歧,应同时呈现正反两面;'证据不足'不要强行断言。引用上述论文标题。"
        ),
    }
    if reject_reason:
        payload["拒答原因"] = reject_reason
    qualified_hints = stance_judge.qualification_conflicts(judgements)
    if qualified_hints:
        payload["限定条件"] = qualified_hints
    payload["structured_answer"] = _structured_answer(
        claim=claim,
        verdict=verdict,
        evidence=evidence[:4],
        reason=reject_reason or "",
        judgement_mode="stance",
        qualification_hints=qualified_hints,
    )

    # 矛盾即资产 (roadmap Step 2): persistence is explicit because it mutates a
    # derived asset. Ordinary verification remains a read-only research action.
    # Only accepted non-neutral evidence may be persisted.
    # Low-confidence, qualifier-mismatched and sentence-unverifiable judgements
    # remain in the response for auditability, but must not pollute the dispute map.
    from backend.app.services.stance.store import record_stances

    accepted_evidence = [
        {**item, "判定版本": stance_judge.JUDGE_VERSION}
        for item, judgement in zip(evidence, judgements)
        if countable(judgement) and judgement.stance in {"SUPPORT", "CONTRADICT"}
    ]
    if accepted_evidence and persist:
        written = record_stances(claim, verdict, accepted_evidence)
        if written == len(accepted_evidence):
            payload["资产写入"] = {"状态": "已写入", "记录数": written}
        else:
            # Do not report a derived evidence asset as available unless every
            # accepted row was durably recorded. The verdict remains usable,
            # while the write failure stays visible to callers and audit logs.
            payload["资产写入"] = {
                "状态": "未写入",
                "原因": "stance 资产写入未完整确认，不能读取为争议资产。",
                "已确认记录数": written,
                "应写入记录数": len(accepted_evidence),
            }
    elif accepted_evidence:
        payload["资产写入"] = {"状态": "未写入", "原因": "未请求 persist=true"}
    return json.dumps(payload, ensure_ascii=False)


TOOL = Tool(
    name="verify_claim",
    schema=SCHEMA,
    run=run,
    side_effect="write",
    check_permissions=_check_persist_permission,
    prompt_fragment="先检索再逐条判定证据立场(支持/反驳/中立)与置信度,置信不足或限定条件不匹配时如实报证据不足",
)
