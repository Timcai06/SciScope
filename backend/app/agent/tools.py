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
            "name": "summarize_field",
            "description": "针对某主题检索一批代表论文,作为撰写'领域小综述/研究现状'的素材。用于'综述/研究现状/概览/有哪些进展'类任务。",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "description": "领域/主题"}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_papers",
            "description": "取两篇论文的详情用于对比。用于'对比/比较 A 与 B 两篇论文'。需要两个 paper_id(可先用 search 拿到)。",
            "parameters": {
                "type": "object",
                "properties": {"paper_id_a": {"type": "string"}, "paper_id_b": {"type": "string"}},
                "required": ["paper_id_a", "paper_id_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_bibliography",
            "description": "把若干 paper_id 导出为 BibTeX 引文条目。用于'导出引用/参考文献/BibTeX'。",
            "parameters": {
                "type": "object",
                "properties": {"paper_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["paper_ids"],
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
    {
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
        if name == "summarize_field":
            return _summarize_field(args)
        if name == "compare_papers":
            return _compare_papers(args)
        if name == "export_bibliography":
            return _export_bibliography(args)
        if name == "query_knowledge_graph":
            return _graph(args)
        if name == "verify_claim":
            return _verify_claim(args)
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
    items = []
    for r in results:
        # snippet is the matched chunk ("title. abstract…") — strip the leading
        # title so it reads as a pure abstract excerpt and is never confused with
        # author names by the model.
        snippet = (r.snippet or "").strip()
        title = (r.title or "").strip()
        if title and snippet.lower().startswith(title.lower()):
            snippet = snippet[len(title):].lstrip(" .。:：-—")
        items.append(
            {
                "paper_id": r.paper_id,
                "标题": title,
                "年份": r.year,
                "作者": (r.authors or [])[:3],
                "摘要片段": snippet[:200],
            }
        )
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


def _summarize_field(args: dict[str, Any]) -> str:
    from backend.app.services import retrieval_service

    topic = str(args.get("topic") or "").strip()
    if not topic:
        return "summarize_field: topic 为空"
    results = retrieval_service.search(topic, limit=10)
    if not results:
        return f"未检索到关于 '{topic}' 的论文。"
    items = []
    for r in results:
        snippet = (r.snippet or "").strip()
        title = (r.title or "").strip()
        if title and snippet.lower().startswith(title.lower()):
            snippet = snippet[len(title):].lstrip(" .。:：-—")
        items.append({"标题": title, "年份": r.year, "摘要片段": snippet[:160]})
    return json.dumps({"主题": topic, "素材论文": items, "提示": "请据此综述研究现状,引用标题"}, ensure_ascii=False)


def _compare_papers(args: dict[str, Any]) -> str:
    a = _get_paper({"paper_id": args.get("paper_id_a", "")})
    b = _get_paper({"paper_id": args.get("paper_id_b", "")})
    return json.dumps({"论文A": _maybe_json(a), "论文B": _maybe_json(b),
                       "提示": "请从方法/数据/结论等维度对比两篇论文"}, ensure_ascii=False)


def _export_bibliography(args: dict[str, Any]) -> str:
    from backend.app.core.config import get_settings

    ids = args.get("paper_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    ids = [str(x).strip() for x in ids if str(x).strip()]
    if not ids:
        return "export_bibliography: paper_ids 为空"
    dsn = get_settings().db_dsn
    if not dsn:
        return "数据库不可用。"
    import psycopg

    entries = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for pid in ids[:20]:
            cur.execute(
                """
                SELECT p.paper_uid, p.title, p.year,
                       coalesce(p.metadata->>'paper_id', p.source_id) AS pid
                FROM papers p
                WHERE p.paper_uid = %(id)s OR p.source_id = %(id)s OR p.metadata->>'paper_id' = %(id)s
                LIMIT 1
                """,
                {"id": pid},
            )
            row = cur.fetchone()
            if not row:
                continue
            uid, title, year, real_pid = row
            cur.execute(
                "SELECT a.name FROM paper_authors pa JOIN authors a ON a.author_uid=pa.author_uid "
                "WHERE pa.paper_uid=%s ORDER BY pa.author_position LIMIT 10",
                (uid,),
            )
            authors = [r[0] for r in cur.fetchall()]
            surname = (authors[0].split()[-1] if authors else "anon").lower()
            key = f"{surname}{year or ''}"
            auth = " and ".join(authors) if authors else "Unknown"
            entries.append(
                f"@article{{{key},\n  title={{{title}}},\n  author={{{auth}}},\n  year={{{year or 'n.d.'}}},\n  note={{{real_pid}}}\n}}"
            )
    if not entries:
        return "未找到这些 paper_id 对应的论文。"
    return "\n\n".join(entries)


def _maybe_json(s: str):
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s


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


def _verify_claim(args: dict[str, Any]) -> str:
    """Fact-check a claim against the corpus via cross-lingual semantic grounding.

    Retrieves evidence, then scores claim<->evidence with the e5 embedder (the same
    cross-lingual space used for retrieval), so a Chinese claim can be grounded on
    English literature. Returns a support verdict + citable sources — not a yes/no
    oracle, but a calibrated grounding signal the model must interpret honestly.
    """
    from backend.app.core.config import get_settings
    from backend.app.services import retrieval_service
    from src.models.embeddings import get_embedder

    claim = str(args.get("claim") or "").strip()
    if not claim:
        return "verify_claim: claim 为空"

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

    evidence = [
        {**meta, "接地相似度": round(sim, 3)}
        for sim, meta in ranked[:4]
    ]
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
