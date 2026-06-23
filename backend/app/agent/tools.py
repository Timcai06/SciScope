"""Agent tools: SciScope capabilities exposed as LLM-callable functions.

Each tool wraps an existing service (retrieval / trends / recommend / graph) and
returns a compact, token-efficient string for the model to reason over. The
OpenAI-style schemas in ``TOOL_SCHEMAS`` are sent to the local LLM so it can pick
and call tools itself (agentic orchestration) instead of a fixed pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
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
    },
    {
        "type": "function",
        "function": {
            "name": "get_trends",
            "description": (
                "查询某关键词/主题的研究趋势:动量、burst、Mann-Kendall 趋势判定、Sen's 斜率、"
                "下一年预测。用于'趋势/热度/发展/演进/前景'类问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string", "description": "关键词或主题(英文优先)"}},
                "required": ["keyword"],
            },
        },
    },
    {
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
    },
    {
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
    },
]


def execute_tool(name: str, args: dict[str, Any]) -> str:
    """Dispatch a tool call; always returns a string (errors included)."""
    try:
        if name == "search_literature":
            return _search(args)
        if name == "get_trends":
            return _trends(args)
        if name == "recommend_papers":
            return _recommend(args)
        if name == "query_knowledge_graph":
            return _graph(args)
        return f"未知工具: {name}"
    except Exception as exc:  # noqa: BLE001 — surface failures to the model, don't crash the loop
        return f"工具 {name} 执行出错: {type(exc).__name__}: {exc}"


def _search(args: dict[str, Any]) -> str:
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
            "title": r.title,
            "year": r.year,
            "authors": (r.authors or [])[:3],
            "snippet": (r.snippet or "")[:200],
        }
        for r in results
    ]
    return json.dumps(items, ensure_ascii=False)


def _trends(args: dict[str, Any]) -> str:
    keyword = str(args.get("keyword") or "").strip().lower()
    if not keyword:
        return "get_trends: keyword 为空"
    path = Path("models/trends/hot_keywords.csv")
    if not path.exists():
        return "趋势模型未构建(models/trends/hot_keywords.csv 缺失)。"
    import csv

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    matches = [r for r in rows if keyword in str(r.get("keyword", "")).lower()]
    if not matches:
        # fall back to nearest by token overlap
        toks = set(keyword.split())
        matches = sorted(
            rows,
            key=lambda r: len(toks & set(str(r.get("keyword", "")).lower().split())),
            reverse=True,
        )[:1]
        matches = [m for m in matches if toks & set(str(m.get("keyword", "")).lower().split())]
    if not matches:
        return f"未找到与 '{keyword}' 匹配的趋势关键词。"
    out = []
    for r in matches[:3]:
        out.append(
            {
                "关键词": r.get("keyword"),
                "累计论文数": r.get("doc_count"),
                "趋势判定": r.get("mk_trend"),  # rising / falling / increasing / no-trend
                "稳健斜率Sen": r.get("sen_slope"),
                "动量分": r.get("momentum_score"),
                "爆发分": r.get("burst_score"),
                "预测目标年份": r.get("forecast_next_year"),  # 这是年份,非数量
                "该年预测归一化词频": r.get("forecast_normalized_df"),
                "生命周期阶段": r.get("lifecycle_stage"),
            }
        )
    return json.dumps(out, ensure_ascii=False)


def _recommend(args: dict[str, Any]) -> str:
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


def _graph(args: dict[str, Any]) -> str:
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
