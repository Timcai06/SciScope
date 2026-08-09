"""recommend_papers — similar-paper recommendations for a known paper_id.

G02 查询解释合同：
- ``paper_embeddings`` 表不存在 → 结构化 ``unavailable``，reason 固定为
  ``paper_embeddings_unavailable``，**绝不** fallback 成伪造的“语义推荐成功”；
- 服务可用但无候选 → 结构化 ``empty``；
- 成功 → 每条推荐带 paper_id / title / year / field / similarity /
  shared_keywords，并附数据源说明。
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool
from backend.app.agent.tools._validators import v_paper_id

SCHEMA = {
    "type": "function",
    "function": {
        "name": "recommend_papers",
        "description": "给定一篇论文的 paper_id,推荐相似论文(语义+关键词+作者+MMR 多样性)。仅在已知具体 paper_id 时调用。",
        "parameters": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
}

# 固定、可测试的不可用原因（G02 合同要求）。
UNAVAILABLE_REASON = "paper_embeddings_unavailable"


def run(args: dict[str, Any]) -> str:
    from backend.app.services import recommend_service

    paper_id = str(args.get("paper_id") or "").strip()
    if not paper_id:
        return json.dumps(
            {"status": "empty", "results": [], "unavailable_reason": None,
             "note": "paper_id 为空", "data_source": None},
            ensure_ascii=False,
        )

    if not recommend_service.is_available():
        return json.dumps(
            {
                "status": "unavailable",
                "query": {"kind": "recommend", "paper_id": paper_id},
                "data_source": None,
                "results": [],
                "unavailable_reason": UNAVAILABLE_REASON,
                "note": "paper_embeddings 缺失（2080 Ti 全量构建未完成，见 G03）；"
                        "不提供伪造的语义推荐。",
            },
            ensure_ascii=False,
        )

    recs = recommend_service.recommend(paper_id, limit=5)
    if not recs:
        return json.dumps(
            {
                "status": "empty",
                "query": {"kind": "recommend", "paper_id": paper_id},
                "data_source": "recommend_service",
                "results": [],
                "unavailable_reason": None,
                "note": f"未为 {paper_id} 找到相似论文（paper 不存在或无候选）。",
            },
            ensure_ascii=False,
        )
    items = [
        {
            "paper_id": r.paper_id,
            "title": r.title,
            "year": r.year,
            "field": r.field,
            "similarity": r.semantic_similarity,
            "shared_keywords": r.shared_keywords[:5],
            "factors": r.factors,
        }
        for r in recs
    ]
    return json.dumps(
        {
            "status": "ok",
            "query": {"kind": "recommend", "paper_id": paper_id},
            "data_source": "recommend_service",
            "results": items,
            "unavailable_reason": None,
            "note": "推荐基于 paper_embeddings 语义近邻 + 关键词/作者重叠 + MMR 重排；"
                    "相关性为计算相似度，不代表科学结论支持。",
        },
        ensure_ascii=False,
    )


TOOL = Tool(
    name="recommend_papers",
    schema=SCHEMA,
    run=run,
    validate=v_paper_id,
    prompt_fragment="给定真实 paper_id,推荐相似论文",
)
