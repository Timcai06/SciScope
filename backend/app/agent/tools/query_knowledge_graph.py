"""query_knowledge_graph — research communities / author-keyword-topic graphs."""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool

SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_knowledge_graph",
        "description": (
            "查询知识图谱。type=community 返回研究社区主题(各社区的代表关键词);"
            "type=author/keyword/topic 返回对应图谱,center 可选(以某作者/关键词为中心)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "community / author / keyword / topic"},
                "center": {"type": "string", "description": "中心实体,可选"},
            },
            "required": ["type"],
        },
    },
}


def run(args: dict[str, Any]) -> str:
    from backend.app.services import graph_service

    gtype = str(args.get("type") or "keyword").strip().lower()
    center = (args.get("center") or "").strip() or None
    if gtype in ("community", "communities", "社区"):
        data = graph_service.graph("keyword", limit=1)
        comms = data.get("communities", [])[:8]
        if not comms:
            return "知识图谱社区数据不可用。"
        return json.dumps(
            [{"size": c["size"], "top_terms": c["top_terms"][:8]} for c in comms],
            ensure_ascii=False,
        )
    if gtype not in ("author", "keyword", "topic"):
        gtype = "keyword"
    data = graph_service.graph(gtype, center=center, limit=20)
    nodes = [n.get("label") for n in data.get("nodes", [])][:20]
    return json.dumps(
        {"type": gtype, "center": center, "node_count": len(data.get("nodes", [])),
         "edge_count": len(data.get("edges", [])), "nodes": nodes},
        ensure_ascii=False,
    )


TOOL = Tool(
    name="query_knowledge_graph",
    schema=SCHEMA,
    run=run,
    prompt_fragment="查知识图谱/研究社区(作者/关键词/主题)",
)
