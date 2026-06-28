"""verify_claim — fact-check a claim via cross-lingual semantic grounding."""

from __future__ import annotations

import json
from typing import Any, Iterator

from backend.app.agent.tools.base import Tool

SCHEMA = {
    "type": "function",
    "function": {
        "name": "verify_claim",
        "description": (
            "核查一句论断是否有文献证据支持:检索相关文献,并用跨语言语义相似度度量"
            "「论断↔证据」的接地程度,返回支持等级(强支持/部分支持/证据不足)与可引用的出处。"
            "用于'这个说法对吗/有没有依据/求证 X'类问题,或在你给出关键论断前自我核验。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"claim": {"type": "string", "description": "需要核查的一句论断,中英文均可"}},
            "required": ["claim"],
        },
    },
}


def run(args: dict[str, Any]) -> Iterator[str]:
    """Generator handler: streams the retrieve→score phases, returns the verdict.

    Retrieves evidence, then scores claim<->evidence with the e5 embedder (the
    same cross-lingual space used for retrieval), so a Chinese claim can be
    grounded on English literature. Returns a support verdict + citable sources —
    not a yes/no oracle, but a calibrated grounding signal to interpret honestly.
    """
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

    # Build evidence texts (title + abstract excerpt) and score grounding.
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

    ranked = sorted(zip(sims, evid_meta), key=lambda x: x[0], reverse=True)
    top = ranked[0][0]
    # e5 cross-lingual (CN claim -> EN evidence) cosine caps lower than monolingual:
    # ~0.84+ = on-claim support, ~0.78-0.84 = partial, below = weak.
    if top >= 0.84:
        verdict = "强支持"
    elif top >= 0.78:
        verdict = "部分支持"
    else:
        verdict = "证据不足"

    evidence = [{**meta, "接地相似度": round(sim, 3)} for sim, meta in ranked[:4]]
    return json.dumps(
        {
            "论断": claim,
            "支持等级": verdict,
            "最高接地相似度": round(top, 3),
            "证据": evidence,
            "提示": "请据证据如实表述支持程度,引用上述论文标题;若为'证据不足'不要强行断言。",
        },
        ensure_ascii=False,
    )


TOOL = Tool(
    name="verify_claim",
    schema=SCHEMA,
    run=run,
    prompt_fragment="用跨语言语义接地度核查一句论断是否有文献支持",
)
