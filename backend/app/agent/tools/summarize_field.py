"""summarize_field — gather representative papers as review material."""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool
from backend.app.agent.tools._common import clean_snippet

SCHEMA = {
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
}


def run(args: dict[str, Any]) -> str:
    from backend.app.services import retrieval_service

    topic = str(args.get("topic") or "").strip()
    if not topic:
        return "summarize_field: topic 为空"
    results = retrieval_service.search(topic, limit=10)
    if not results:
        return f"未检索到关于 '{topic}' 的论文。"
    items = [
        {"标题": (r.title or "").strip(), "年份": r.year, "摘要片段": clean_snippet(r.snippet, r.title, limit=160)}
        for r in results
    ]
    return json.dumps({"主题": topic, "素材论文": items, "提示": "请据此综述研究现状,引用标题"}, ensure_ascii=False)


TOOL = Tool(
    name="summarize_field",
    schema=SCHEMA,
    run=run,
    prompt_fragment="取某主题的代表论文,作为“领域小综述/研究现状”的素材",
)
