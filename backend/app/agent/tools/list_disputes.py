"""list_disputes — read the accepted-evidence scientific dispute frontier."""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool
from backend.app.services.stance.store import disputed_claims

SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_disputes",
        "description": (
            "读取 SciScope 已沉淀的科学争议前线: 仅返回同时具有可采信支持证据和反驳证据的论断。"
            "适用于'有哪些争议/正反证据冲突/争议地图'类问题;空结果表示当前资产中尚无满足条件的争议,"
            "不是证明不存在科学分歧。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
        },
    },
}


def run(args: dict[str, Any]) -> str:
    """Return compact, read-only dispute rows for agent synthesis."""
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    rows = disputed_claims(limit=limit)
    return json.dumps(
        {
            "争议数量": len(rows),
            "争议": rows,
            "边界": "仅计入有可核验证据句、置信度达阈值且无适用条件冲突的 SUPPORT/CONTRADICT 证据。",
        },
        ensure_ascii=False,
    )


TOOL = Tool(
    name="list_disputes",
    schema=SCHEMA,
    run=run,
    prompt_fragment="查科学争议地图/正反证据前线(只读,空结果不等于不存在争议)",
)
