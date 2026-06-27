"""get_trends — research-trend evidence for a keyword/topic."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from backend.app.agent.tools.base import Tool

SCHEMA = {
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
}


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


def run(args: dict[str, Any]) -> str:
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


TOOL = Tool(
    name="get_trends",
    schema=SCHEMA,
    run=run,
    prompt_fragment="查某关键词/主题的研究趋势(增长方向、阶段、预测)",
)
