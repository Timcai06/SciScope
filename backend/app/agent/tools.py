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
            "name": "get_paper",
            "description": "按 paper_id 获取某篇论文的详细信息(标题/年份/作者/领域/摘要)。用于深入了解某篇具体论文,或在检索后取细节。",
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
        if name == "get_paper":
            return _get_paper(args)
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


def _kw_match(rows: list[dict], keyword: str) -> list[dict]:
    """Substring matches, exact keyword first, then by descending doc_count."""
    hits = [r for r in rows if keyword in str(r.get("keyword", "")).lower()]

    def rank(r: dict) -> tuple:
        exact = str(r.get("keyword", "")).lower() == keyword
        try:
            dc = int(r.get("doc_count") or 0)
        except (TypeError, ValueError):
            dc = 0
        return (exact, dc)

    return sorted(hits, key=rank, reverse=True)


def _trends(args: dict[str, Any]) -> str:
    import csv

    keyword = str(args.get("keyword") or "").strip().lower()
    if not keyword:
        return "get_trends: keyword 为空"

    # 1) Top-tracked keywords — full stats incl. Mann-Kendall / Sen's slope.
    hot = Path("models/trends/hot_keywords.csv")
    if hot.exists():
        matches = _kw_match(list(csv.DictReader(hot.open(encoding="utf-8"))), keyword)
        if matches:
            out = [
                {
                    "关键词": r.get("keyword"),
                    "累计论文数": r.get("doc_count"),
                    "趋势判定": r.get("mk_trend"),
                    "稳健斜率Sen": r.get("sen_slope"),
                    "动量分": r.get("momentum_score"),
                    "爆发分": r.get("burst_score"),
                    "预测目标年份": r.get("forecast_next_year"),  # 年份,非数量
                    "该年预测归一化词频": r.get("forecast_normalized_df"),
                    "生命周期阶段": r.get("lifecycle_stage"),
                }
                for r in matches[:3]
            ]
            return json.dumps(out, ensure_ascii=False)

    # 2) Full keyword universe — basic momentum/burst/growth (no MK).
    full = Path("data/analysis/keyword_trends.csv")
    if full.exists():
        with full.open(encoding="utf-8") as f:
            matches = _kw_match(list(csv.DictReader(f)), keyword)
        if matches:
            out = []
            for r in matches[:3]:
                try:
                    growth = float(r.get("growth_rate") or 0)
                except (TypeError, ValueError):
                    growth = 0.0
                out.append(
                    {
                        "关键词": r.get("keyword"),
                        "累计论文数": r.get("doc_count"),
                        "趋势判定": "rising" if growth > 0.05 else ("falling" if growth < -0.05 else "stable"),
                        "增长率": r.get("growth_rate"),
                        "动量分": r.get("momentum_score"),
                        "爆发分": r.get("burst_score"),
                        "说明": "来自全量关键词趋势(非 top 热点,无 MK 检验)",
                    }
                )
            return json.dumps(out, ensure_ascii=False)

    return f"未找到与 '{keyword}' 匹配的趋势数据(可能不是被收录的关键词)。"


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


def _get_paper(args: dict[str, Any]) -> str:
    from backend.app.core.config import get_settings

    paper_id = str(args.get("paper_id") or "").strip()
    if not paper_id:
        return "get_paper: paper_id 为空"
    dsn = get_settings().db_dsn
    if not dsn:
        return "数据库不可用。"
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, year, field, abstract,
                   coalesce(metadata->>'paper_id', source_id) AS pid
            FROM papers
            WHERE paper_uid = %(id)s OR source_id = %(id)s OR metadata->>'paper_id' = %(id)s
            LIMIT 1
            """,
            {"id": paper_id},
        )
        row = cur.fetchone()
        if not row:
            return f"未找到 paper_id={paper_id} 的论文。"
        title, year, field, abstract, pid = row
        cur.execute(
            """
            SELECT a.name FROM paper_authors pa JOIN authors a ON a.author_uid = pa.author_uid
            JOIN papers p ON p.paper_uid = pa.paper_uid
            WHERE p.metadata->>'paper_id' = %(id)s OR p.source_id = %(id)s OR p.paper_uid = %(id)s
            ORDER BY pa.author_position LIMIT 8
            """,
            {"id": paper_id},
        )
        authors = [r[0] for r in cur.fetchall()]
    return json.dumps(
        {"paper_id": pid, "title": title, "year": year, "field": field,
         "authors": authors, "abstract": (abstract or "")[:800]},
        ensure_ascii=False,
    )


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
