"""export_bibliography — render papers as BibTeX entries."""

from __future__ import annotations

from typing import Any, Iterator

from backend.app.agent.tools.base import Tool
from backend.app.agent.tools._common import db_dsn
from backend.app.agent.tools._validators import v_export

SCHEMA = {
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
}


def run(args: dict[str, Any]) -> Iterator[str]:
    """Generator handler: yields per-paper progress, returns the BibTeX blob.

    A read-only DB lookup that can touch up to 20 papers, so it streams progress
    to demonstrate the Tool streaming contract end to end.
    """
    ids = args.get("paper_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    ids = [str(x).strip() for x in ids if str(x).strip()]
    if not ids:
        return "export_bibliography: paper_ids 为空"
    dsn = db_dsn()
    if not dsn:
        return "数据库不可用。"
    import psycopg

    entries: list[str] = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        targets = ids[:20]
        for n, pid in enumerate(targets, 1):
            yield f"导出引文 {n}/{len(targets)}…"
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


TOOL = Tool(
    name="export_bibliography",
    schema=SCHEMA,
    run=run,
    validate=v_export,
    max_result_chars=20000,  # BibTeX for up to 20 papers can run long
    prompt_fragment="把若干真实 paper_id 导出为 BibTeX 引文",
)
