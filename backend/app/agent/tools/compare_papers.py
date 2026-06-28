"""compare_papers — fetch two papers' details for side-by-side comparison."""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool
from backend.app.agent.tools._common import maybe_json
from backend.app.agent.tools._validators import v_compare
from backend.app.agent.tools.get_paper import run as get_paper_run

SCHEMA = {
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
}


def run(args: dict[str, Any]) -> str:
    a = get_paper_run({"paper_id": args.get("paper_id_a", "")})
    b = get_paper_run({"paper_id": args.get("paper_id_b", "")})
    return json.dumps(
        {"论文A": maybe_json(a), "论文B": maybe_json(b), "提示": "请从方法/数据/结论等维度对比两篇论文"},
        ensure_ascii=False,
    )


TOOL = Tool(
    name="compare_papers",
    schema=SCHEMA,
    run=run,
    validate=v_compare,
    prompt_fragment="取两篇真实 paper_id 的论文做对比",
)
