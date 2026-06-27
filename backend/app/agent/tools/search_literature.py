"""search_literature — hybrid retrieval over the literature corpus."""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool
from backend.app.agent.tools._common import clean_snippet

SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_literature",
        "description": (
            "在 16 万篇科技文献库中检索论文(混合检索+跨语言重排)。用于'有哪些论文/"
            "介绍某主题/某领域的方法'等问题。返回最相关论文的 id/标题/年份/作者/片段。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索主题,中英文均可"},
                "year": {"type": "integer", "description": "限定发表年份;不限定填 0"},
            },
            "required": ["query"],
        },
    },
}


def run(args: dict[str, Any]) -> str:
    from backend.app.services import retrieval_service

    query = str(args.get("query") or "").strip()
    if not query:
        return "search_literature: query 为空"
    year = args.get("year") or None
    if year in (0, "0"):
        year = None
    results = retrieval_service.search(query, limit=6, year=int(year) if year else None)
    if not results:
        return "未检索到相关论文。"
    items = [
        {
            "paper_id": r.paper_id,
            "标题": (r.title or "").strip(),
            "年份": r.year,
            "作者": (r.authors or [])[:3],
            "摘要片段": clean_snippet(r.snippet, r.title),
        }
        for r in results
    ]
    return json.dumps(items, ensure_ascii=False)


TOOL = Tool(
    name="search_literature",
    schema=SCHEMA,
    run=run,
    prompt_fragment="在 16 万篇文献库中检索论文,回答“有哪些论文/某主题/某领域的方法”",
)
