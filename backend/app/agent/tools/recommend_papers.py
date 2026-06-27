"""recommend_papers — similar-paper recommendations for a known paper_id."""

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


def run(args: dict[str, Any]) -> str:
    from backend.app.services import recommend_service

    paper_id = str(args.get("paper_id") or "").strip()
    if not paper_id:
        return "recommend_papers: paper_id 为空"
    recs = recommend_service.recommend(paper_id, limit=5)
    if not recs:
        return f"未能为 {paper_id} 生成推荐(可能 paper_id 不存在)。"
    items = [
        {
            "paper_id": r.paper_id,
            "title": r.title,
            "year": r.year,
            "field": r.field,
            "similarity": r.semantic_similarity,
            "shared_keywords": r.shared_keywords[:5],
        }
        for r in recs
    ]
    return json.dumps(items, ensure_ascii=False)


TOOL = Tool(
    name="recommend_papers",
    schema=SCHEMA,
    run=run,
    validate=v_paper_id,
    prompt_fragment="给定真实 paper_id,推荐相似论文",
)
