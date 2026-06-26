"""Agent tools: SciScope capabilities exposed as LLM-callable functions.

Each tool wraps an existing service (retrieval / trends / recommend / graph) and
returns a compact, token-efficient string for the model to reason over. The
OpenAI-style schemas in ``TOOL_SCHEMAS`` are sent to the local LLM so it can pick
and call tools itself (agentic orchestration) instead of a fixed pipeline.

Boundary note: tools are intentionally read-only and map to backend service/table
state (papers/chunks/chunk_embeddings/recommendation assets/graphs). Returned
payloads are evidence references, not raw authoritative facts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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
                "查询某关键词/主题的研究趋势证据,返回增长方向、阶段、预测和统计依据。"
                "用于'趋势/热度/发展/演进/前景'类问题;回答时应把统计依据翻译成自然语言,"
                "不要把动量、burst、Mann-Kendall、Sen's slope 等内部字段直接列给用户。"
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


@dataclass(frozen=True)
class Tool:
    """A SciScope capability as a first-class contract.

    Inspired by Claude Code's tool contract: the agent loop stays thin because
    each tool declares its own concurrency safety, pre-execution validation, and
    result-size bound — the runtime never special-cases individual tools. Adding
    a capability is adding a registry entry, not growing the loop.
    """

    name: str
    schema: dict[str, Any]
    run: Callable[[dict[str, Any]], str]
    is_read_only: bool = True
    # Deterministic pre-execution check. Returns a recovery message to show the
    # model (and skip execution), or None to proceed.
    validate: Callable[[dict[str, Any]], str | None] | None = None
    max_result_chars: int = 8000
    # One-line "when to use me", assembled into the system prompt's tool catalog.
    prompt_fragment: str = ""


_PLACEHOLDER_IDS = {"string", "paper_id", "id", "example", "xxx", "n/a", "none", "null", "0"}
_FABRICATED_NUM = re.compile(r"^0+1?$")  # "0000001" etc. — the model's fabricated-id pattern


def _validate_paper_id(value: Any, field: str = "paper_id") -> str | None:
    """Reject ids the model fabricated instead of retrieving — before the DB sees them.

    Catches the real failure modes (a topic phrase passed as an id, or a
    zero-padded placeholder) and tells the model how to recover. It does NOT
    verify existence; the handler already reports 'not found' for plausible but
    absent ids.
    """
    pid = str(value or "").strip()
    if not pid:
        return f"{field} 为空——请先用 search_literature 检索,用返回的真实 paper_id 再调用。"
    if " " in pid or len(pid) > 80:
        return f"{field}={pid!r} 不像论文 ID(疑似把主题/短语当成 ID)。请先用 search_literature 拿到真实 paper_id。"
    if pid.lower() in _PLACEHOLDER_IDS or _FABRICATED_NUM.match(pid):
        return f"{field}={pid!r} 像是编造的占位 ID。请先用 search_literature 拿到真实 paper_id。"
    return None


def _v_paper_id(args: dict[str, Any]) -> str | None:
    return _validate_paper_id(args.get("paper_id"))


def _v_compare(args: dict[str, Any]) -> str | None:
    return _validate_paper_id(args.get("paper_id_a"), "paper_id_a") or _validate_paper_id(
        args.get("paper_id_b"), "paper_id_b"
    )


def _v_export(args: dict[str, Any]) -> str | None:
    ids = args.get("paper_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    cleaned = [str(x).strip() for x in ids if str(x).strip()]
    if not cleaned:
        return "paper_ids 为空——请先用 search_literature 拿到真实 paper_id。"
    for x in cleaned:
        denial = _validate_paper_id(x, "paper_ids 元素")
        if denial:
            return denial
    return None


def execute_tool(name: str, args: dict[str, Any]) -> str:
    """Run a tool through its contract: validate -> run -> bound result size.

    Always returns a string (validation rejections and errors included) so the
    model can read the outcome and recover rather than the loop crashing.
    """
    tool = _REGISTRY.get(name)
    if tool is None:
        # Unknown tool names are rejected here to keep the call boundary explicit.
        return f"未知工具: {name}"
    try:
        if tool.validate is not None:
            denial = tool.validate(args)
            if denial:
                return f"[未执行] {denial}"
        result = tool.run(args)
    except Exception as exc:  # noqa: BLE001 — surface failures to the model, don't crash the loop
        return f"工具 {name} 执行出错: {type(exc).__name__}: {exc}"
    if isinstance(result, str) and len(result) > tool.max_result_chars:
        result = result[: tool.max_result_chars] + " …(结果过长已截断,请用更具体的参数缩小检索范围)"
    return result


def is_read_only(name: str) -> bool:
    """Whether a tool may run concurrently with others (all current tools are)."""
    tool = _REGISTRY.get(name)
    return tool.is_read_only if tool else True


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
                    "增长方向": r.get("mk_trend"),
                    "统计依据": {
                        "稳健年增长斜率": r.get("sen_slope"),
                        "近期活跃度分": r.get("momentum_score"),
                        "短期加速分": r.get("burst_score"),
                    },
                    "预测目标年份": r.get("forecast_next_year"),  # 年份,非数量
                    "该年预测归一化词频": r.get("forecast_normalized_df"),
                    "生命周期阶段": r.get("lifecycle_stage"),
                    "回答提示": "请说明趋势方向、为何这样判断、预测意味着什么;不要直接罗列内部指标名。",
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
                        "增长方向": "rising" if growth > 0.05 else ("falling" if growth < -0.05 else "stable"),
                        "统计依据": {
                            "阶段增长率": r.get("growth_rate"),
                            "近期活跃度分": r.get("momentum_score"),
                            "短期加速分": r.get("burst_score"),
                        },
                        "说明": "来自全量关键词趋势(非 top 热点,无 MK 检验);回答时翻译为自然语言。",
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


# --- Tool contract registry -------------------------------------------------
# Built after handlers are defined; pairs each LLM-facing schema with its handler
# and optional pre-execution validator. New capabilities (permission checks,
# prompt fragments, MCP/sub-agent tools) become more fields/entries here — the
# runtime stays unchanged.
_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "search_literature": _search,
    "get_trends": _trends,
    "recommend_papers": _recommend,
    "get_paper": _get_paper,
    "summarize_field": _summarize_field,
    "compare_papers": _compare_papers,
    "export_bibliography": _export_bibliography,
    "query_knowledge_graph": _graph,
    "verify_claim": _verify_claim,
}
_VALIDATORS: dict[str, Callable[[dict[str, Any]], str | None]] = {
    "recommend_papers": _v_paper_id,
    "get_paper": _v_paper_id,
    "compare_papers": _v_compare,
    "export_bibliography": _v_export,
}
_MAX_RESULT_CHARS: dict[str, int] = {
    "export_bibliography": 20000,  # BibTeX for up to 20 papers can run long
}
# Each tool's "when to use" line. The system prompt's tool catalog is assembled
# from these (so it never drifts from the actual tool set).
_PROMPT_FRAGMENTS: dict[str, str] = {
    "search_literature": "在 16 万篇文献库中检索论文,回答“有哪些论文/某主题/某领域的方法”",
    "get_trends": "查某关键词/主题的研究趋势(增长方向、阶段、预测)",
    "recommend_papers": "给定真实 paper_id,推荐相似论文",
    "get_paper": "按真实 paper_id 取某篇论文的详情",
    "summarize_field": "取某主题的代表论文,作为“领域小综述/研究现状”的素材",
    "compare_papers": "取两篇真实 paper_id 的论文做对比",
    "export_bibliography": "把若干真实 paper_id 导出为 BibTeX 引文",
    "query_knowledge_graph": "查知识图谱/研究社区(作者/关键词/主题)",
    "verify_claim": "用跨语言语义接地度核查一句论断是否有文献支持",
}


def _build_registry() -> dict[str, Tool]:
    registry: dict[str, Tool] = {}
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"]
        registry[name] = Tool(
            name=name,
            schema=schema,
            run=_HANDLERS[name],
            is_read_only=True,
            validate=_VALIDATORS.get(name),
            max_result_chars=_MAX_RESULT_CHARS.get(name, 8000),
            prompt_fragment=_PROMPT_FRAGMENTS.get(name, ""),
        )
    return registry


_REGISTRY: dict[str, Tool] = _build_registry()
TOOLS: tuple[Tool, ...] = tuple(_REGISTRY.values())


def tools_prompt() -> str:
    """Assemble the tool catalog for the system prompt from each tool's fragment.

    Mirrors Claude Code's per-tool self-description: the catalog the model sees
    is built from the registry, so it never drifts from the actual tool set.
    """
    return "\n".join(
        f"- {t.name}:{t.prompt_fragment}" for t in _REGISTRY.values() if t.prompt_fragment
    )


def register_tools(extra: list[Tool]) -> list[str]:
    """Merge additional tools (e.g. wrapped external MCP tools) into the registry.

    Mutates the shared registry + TOOL_SCHEMAS in place so the agent loop (which
    holds the same TOOL_SCHEMAS list) and execute_tool dispatch pick them up
    without any change to the runtime. Returns the names actually added.
    """
    added: list[str] = []
    for tool in extra:
        if tool.name in _REGISTRY:
            continue
        _REGISTRY[tool.name] = tool
        TOOL_SCHEMAS.append(tool.schema)
        added.append(tool.name)
    return added
