"""verify_claim — fact-check a claim via retrieval + stance judgement.

Two-stage grounding:

1. Retrieve topically-relevant evidence via cross-lingual semantic search.
2. Judge each evidence's *stance* toward the claim — SUPPORT / CONTRADICT /
   NEUTRAL — with the LLM.

Stage 2 is what stage-1 cosine similarity alone cannot do: similarity is
symmetric to negation, so "coffee lowers risk" and "coffee raises risk" retrieve
the same papers and score the same. Stance judgement separates support from
refutation, so a claim and its negation get *different* verdicts, and genuine
disagreement in the literature surfaces as 存在争议.

Fail-safe: if the LLM judge is unavailable (offline / mock mode) the tool falls
back to the legacy similarity-only verdict so it never crashes and stays
reproducible without a live model.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from backend.app.agent.tools.base import Tool

SCHEMA = {
    "type": "function",
    "function": {
        "name": "verify_claim",
        "description": (
            "核查一句论断是否有文献证据支持:先检索相关文献,再用大模型逐条判定证据对论断的"
            "「立场」(支持/反驳/中立),返回支持等级(强支持/部分支持/存在争议/证据反驳/证据不足)"
            "与可引用出处。能区分一句论断与它的反面,并在文献存在分歧时标记「存在争议」。"
            "用于'这个说法对吗/有没有依据/求证 X'类问题,或在你给出关键论断前自我核验。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"claim": {"type": "string", "description": "需要核查的一句论断,中英文均可"}},
            "required": ["claim"],
        },
    },
}

# Cross-lingual e5 cosine (CN claim -> EN evidence) caps lower than monolingual;
# these thresholds only grade *how strongly* supporting evidence is on-claim.
_STRONG_SIM = 0.84
_PARTIAL_SIM = 0.78

_STANCE_LABELS = {"SUPPORT", "CONTRADICT", "NEUTRAL"}


def _judge_stances(claim: str, evidence_texts: list[str]) -> list[str] | None:
    """Ask the LLM to label each evidence's stance toward the claim.

    Returns a list of labels aligned to ``evidence_texts`` (each in
    ``_STANCE_LABELS``), or ``None`` if the judge is unavailable or its reply
    can't be parsed — callers then fall back to similarity-only grading.
    """
    from backend.app.services.deepseek_provider import get_llm_provider

    numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(evidence_texts))
    prompt = (
        "你是严格的科学论断核查员。下面是一句论断和若干条文献证据。\n"
        "对每一条证据,判断它与论断的关系,只能取三者之一:\n"
        "- SUPPORT:该证据支持论断成立;\n"
        "- CONTRADICT:该证据表明论断为假,或指向与论断相反的结论;\n"
        "- NEUTRAL:该证据与论断无关,或不足以判断。\n"
        "只依据证据本身判断,不要用常识补足;论断与证据可能语言不同,按语义判断。\n\n"
        f"论断:{claim}\n证据:\n{numbered}\n\n"
        f"只输出一个 JSON 数组,长度必须为 {len(evidence_texts)},元素依次为每条证据的标签,"
        '例如 ["SUPPORT","NEUTRAL","CONTRADICT"]。不要输出数组以外的任何内容。'
    )
    try:
        raw = get_llm_provider().complete(prompt)
        start, end = raw.find("["), raw.rfind("]")
        labels = json.loads(raw[start : end + 1]) if start != -1 and end != -1 else None
        if not isinstance(labels, list):
            return None
    except Exception:
        return None

    # Coerce to exactly len(evidence_texts): unknown/short -> NEUTRAL.
    out = [(str(x).strip().upper() if str(x).strip().upper() in _STANCE_LABELS else "NEUTRAL") for x in labels]
    out = (out + ["NEUTRAL"] * len(evidence_texts))[: len(evidence_texts)]
    return out


def run(args: dict[str, Any]) -> Iterator[str]:
    """Generator handler: streams retrieve→score→stance phases, returns the verdict."""
    from backend.app.core.config import get_settings
    from backend.app.services import retrieval_service
    from src.models.embeddings import get_embedder

    claim = str(args.get("claim") or "").strip()
    if not claim:
        return "verify_claim: claim 为空"

    yield "检索相关文献中…"
    results = retrieval_service.search(claim, limit=6)
    if not results:
        return json.dumps(
            {"论断": claim, "支持等级": "证据不足", "理由": "未检索到相关文献。", "证据": []},
            ensure_ascii=False,
        )

    # Evidence texts (title + abstract excerpt) + metadata, in retrieval order.
    evid_texts, evid_meta = [], []
    for r in results:
        snippet = (r.snippet or "").strip()
        title = (r.title or "").strip()
        evid_texts.append(f"{title}. {snippet}"[:512])
        evid_meta.append({"paper_id": r.paper_id, "标题": title, "年份": r.year})

    yield "计算跨语言接地相似度中…"
    embedder = get_embedder(get_settings().embedding_model)
    qv = embedder.encode_query(claim)
    pv = embedder.encode_passages(evid_texts)
    sims = [float(sum(a * b for a, b in zip(qv, row))) for row in pv]  # vectors are L2-normalized

    # Rank evidence by grounding similarity; keep texts aligned for stance judging.
    ranked = sorted(zip(sims, evid_meta, evid_texts), key=lambda x: x[0], reverse=True)
    top_sim = ranked[0][0]

    yield "判定证据立场中…"
    stances = _judge_stances(claim, [text for _, _, text in ranked])

    if stances is None:
        # Fail-safe: legacy similarity-only grading (offline / mock mode).
        verdict = "强支持" if top_sim >= _STRONG_SIM else "部分支持" if top_sim >= _PARTIAL_SIM else "证据不足"
        method = "similarity"
        support = contradict = None
    else:
        support = stances.count("SUPPORT")
        contradict = stances.count("CONTRADICT")
        support_sims = [sim for (sim, _, _), st in zip(ranked, stances) if st == "SUPPORT"]
        if support and contradict:
            verdict = "存在争议"
        elif contradict:
            verdict = "证据反驳"
        elif support:
            verdict = "强支持" if max(support_sims) >= _STRONG_SIM else "部分支持"
        else:
            verdict = "证据不足"
        method = "stance"

    evidence = []
    for i, (sim, meta, _text) in enumerate(ranked[:4]):
        item = {**meta, "接地相似度": round(sim, 3)}
        if stances is not None:
            item["立场"] = stances[i]
        evidence.append(item)

    payload: dict[str, Any] = {
        "论断": claim,
        "支持等级": verdict,
        "判定方式": method,
        "最高接地相似度": round(top_sim, 3),
        "证据": evidence,
        "提示": (
            "请据证据如实表述:'证据反驳'表示文献与论断相反,不要断言论断成立;"
            "'存在争议'表示文献有分歧,应同时呈现正反两面;'证据不足'不要强行断言。引用上述论文标题。"
        ),
    }
    if stances is not None:
        payload["证据立场统计"] = {"支持": support, "反驳": contradict, "中立": len(stances) - support - contradict}
        # 矛盾即资产 (roadmap Step 2): accumulate judged stances so contradictions
        # build the 争议地图 over time. Persist every judged evidence (not just the
        # displayed top 4). Fail-open inside — never blocks the answer.
        from backend.app.services.stance_store import record_stances

        record_stances(
            claim,
            verdict,
            [
                {**meta, "接地相似度": round(sim, 3), "立场": stances[i]}
                for i, (sim, meta, _text) in enumerate(ranked)
            ],
        )
    return json.dumps(payload, ensure_ascii=False)


TOOL = Tool(
    name="verify_claim",
    schema=SCHEMA,
    run=run,
    prompt_fragment="先检索再逐条判定证据立场(支持/反驳/中立),核查论断是否被文献支持",
)
