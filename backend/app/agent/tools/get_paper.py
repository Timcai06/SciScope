"""get_paper — full detail for one paper by paper_id."""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool
from backend.app.agent.tools._common import db_dsn
from backend.app.agent.tools._validators import v_paper_id

SCHEMA = {
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
}


def run(args: dict[str, Any]) -> str:
    paper_id = str(args.get("paper_id") or "").strip()
    if not paper_id:
        return "get_paper: paper_id 为空"
    dsn = db_dsn()
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


TOOL = Tool(
    name="get_paper",
    schema=SCHEMA,
    run=run,
    validate=v_paper_id,
    prompt_fragment="按真实 paper_id 取某篇论文的详情",
)
