"""paper_structured — 按 paper_id 返回结构化科学信息（D03/D05 出口）。

只读工具：读取 D03 结构化中间层与 D01 准入记录，返回带来源/置信度/许可边界的
字段视图；未抽取或未授权展示的字段不输出确定值。不查数据库、不写任何状态。
"""

from __future__ import annotations

import json
import os
from typing import Any

from backend.app.agent.tools.base import Tool
from src.infra.structured_export import (
    DEFAULT_ADMISSION_PATH,
    DEFAULT_STRUCTURED_PATH,
    load_admission_index,
    load_structured_index,
    query_structured,
)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "paper_structured",
        "description": (
            "按 paper_id 获取某篇论文的结构化科学信息（研究对象/研究设计/主要结果/数值与单位/"
            "限制条件/结论句），每个字段带来源 chunk、置信度与许可边界；未抽取或未授权展示的字段"
            "不输出确定值。用于需要字段级结构化证据的场景。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "论文稳定 ID（如 PX-001）"},
                "source": {"type": "string", "description": "来源标识（可选；缺省且多来源同名时返回 matches）"},
            },
            "required": ["paper_id"],
        },
    },
}


def _index_path(env_name: str, default: str) -> str:
    return os.environ.get(env_name) or default


def run(args: dict[str, Any]) -> str:
    paper_id = str(args.get("paper_id") or "").strip()
    source = str(args.get("source") or "").strip() or None
    if not paper_id:
        return "paper_structured: paper_id 为空"

    structured_path = _index_path("SCISCOPE_STRUCTURED_PATH", DEFAULT_STRUCTURED_PATH)
    admission_path = _index_path("SCISCOPE_ADMISSION_PATH", DEFAULT_ADMISSION_PATH)

    structured_index = load_structured_index(structured_path)
    if not structured_index:
        return (
            f"paper_structured: 结构化索引未就绪（{structured_path} 不存在或为空）。"
            "该能力依赖 D02/D03 中间层产物，当前数据层未生成。"
        )
    admission_index = load_admission_index(admission_path)

    view = query_structured(
        paper_id,
        source,
        structured_index=structured_index,
        admission_index=admission_index,
    )
    return json.dumps(view, ensure_ascii=False)


TOOL = Tool(
    name="paper_structured",
    schema=SCHEMA,
    run=run,
    side_effect="read",
    prompt_fragment="按真实 paper_id 获取某篇论文的结构化科学信息（字段级、带来源 chunk、置信度与许可边界；未抽取/未授权不输出确定值）",
)
