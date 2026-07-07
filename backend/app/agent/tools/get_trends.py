"""get_trends — research-trend evidence for a keyword/topic."""

from __future__ import annotations

import csv
import json
import re
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


# Direction values come from the trend tables in English; spell them out in
# Chinese so the model can't misread falling as growth.
_DIRECTION_CN = {
    "rising": "rising(上升)",
    "increasing": "increasing(上升)",
    "falling": "falling(下降)",
    "decreasing": "decreasing(下降)",
    "stable": "stable(平稳)",
    "no-trend": "no-trend(无明显趋势)",
}


def _direction_cn(value: Any) -> Any:
    return _DIRECTION_CN.get(str(value or "").strip().lower(), value)


def _significance(mk_p: Any) -> str:
    """Verbalize the Mann-Kendall p-value so weak trends can't be overread."""
    try:
        p = float(mk_p)
    except (TypeError, ValueError):
        return "未知"
    if p < 0.1:
        return f"显著(p={p:.3f})"
    return f"不显著(p={p:.2f}),方向仅供参考,不要下强结论"


def _normalize(text: str) -> str:
    """Fold case/punctuation so 'Retrieval-Augmented Generation' matches the
    indexed 'retrieval augmented generation'."""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z一-鿿]+", " ", text.lower())).strip()


def _kw_match(rows: list[dict], keyword: str) -> list[dict]:
    """Normalized substring matches, exact keyword first, then by doc_count."""
    needle = _normalize(keyword)
    hits = [r for r in rows if needle in _normalize(str(r.get("keyword", "")))]

    def rank(r: dict) -> tuple:
        exact = _normalize(str(r.get("keyword", ""))) == needle
        try:
            dc = int(r.get("doc_count") or 0)
        except (TypeError, ValueError):
            dc = 0
        return (exact, dc)

    return sorted(hits, key=rank, reverse=True)


def _variant_key(keyword: str) -> str:
    """Singular/plural-folded token-set key: 'graph neural networks gnn' and
    'graph neural network gnn' collapse to the same key."""
    tokens = (t.rstrip("s") if len(t) > 3 else t for t in _normalize(keyword).split())
    return " ".join(sorted(tokens))


def _fold_variants(matches: list[dict]) -> list[tuple[dict, list[str], bool]]:
    """Group near-duplicate keyword rows; one representative per group.

    The trend tables index singular/plural/abbreviation variants as separate
    keywords with independently-computed (and sometimes opposite) trends —
    presenting them side by side reads as a contradiction. Returns, per group:
    (representative row = best-ranked match, other variant spellings, whether
    the group's direction labels disagree).
    """
    groups: dict[str, list[dict]] = {}
    for r in matches:  # matches are already ranked best-first
        groups.setdefault(_variant_key(str(r.get("keyword", ""))), []).append(r)
    out: list[tuple[dict, list[str], bool]] = []
    for rows in groups.values():
        rep = rows[0]
        variants = [str(r.get("keyword", "")) for r in rows[1:]]
        directions = {str(r.get("mk_trend") or "").strip().lower() for r in rows} - {""}
        out.append((rep, variants, len(directions) > 1))
    return out


def _suggest(rows: list[dict], keyword: str, limit: int = 5) -> list[str]:
    """Indexed keywords sharing tokens with the query, best matches first.

    A compound query like 'federated learning privacy' misses as a whole but
    its parts are indexed; surfacing them lets the model retry once usefully.
    """
    tokens = [t for t in _normalize(keyword).split() if len(t) > 2]
    if not tokens:
        return []
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for r in rows:
        raw = str(r.get("keyword", ""))
        kw = _normalize(raw)
        if kw in seen:
            continue
        seen.add(kw)
        overlap = sum(1 for t in tokens if t in kw)
        if not overlap:
            continue
        try:
            dc = int(r.get("doc_count") or 0)
        except (TypeError, ValueError):
            dc = 0
        scored.append((overlap, dc, raw))
    scored.sort(reverse=True)
    return [kw for _, _, kw in scored[:limit]]


def run(args: dict[str, Any]) -> str:
    keyword = str(args.get("keyword") or "").strip().lower()
    if not keyword:
        return "get_trends: keyword 为空"

    hot_rows: list[dict] = []
    # 1) Top-tracked keywords — full stats incl. Mann-Kendall / Sen's slope.
    hot = Path("models/trends/hot_keywords.csv")
    if hot.exists():
        hot_rows = list(csv.DictReader(hot.open(encoding="utf-8")))
        matches = _kw_match(hot_rows, keyword)
        if matches:
            out = []
            for rep, variants, conflicting in _fold_variants(matches)[:3]:
                item = {
                    "关键词": rep.get("keyword"),
                    "累计论文数": rep.get("doc_count"),
                    "增长方向": _direction_cn(rep.get("mk_trend")),
                    "趋势显著性": _significance(rep.get("mk_p")),
                    "统计依据": {
                        "稳健年增长斜率": rep.get("sen_slope"),
                        "近期活跃度分": rep.get("momentum_score"),
                        "短期加速分": rep.get("burst_score"),
                    },
                    "预测目标年份": rep.get("forecast_next_year"),  # 年份,非数量
                    "该年预测归一化词频": rep.get("forecast_normalized_df"),
                    "生命周期阶段": rep.get("lifecycle_stage"),
                    "回答提示": (
                        "请说明趋势方向、为何这样判断、预测意味着什么;不要直接罗列内部指标名。"
                        "趋势不显著或样本小时,如实说明方向不可靠。"
                    ),
                }
                if variants:
                    item["同义变体"] = variants
                if conflicting:
                    item["变体提醒"] = (
                        "该关键词的同义变体各自统计出的方向不一致(样本小、均不可靠),"
                        "不要据此断言趋势方向,应以论文数更多的行为主并说明不确定性。"
                    )
                out.append(item)
            return json.dumps(out, ensure_ascii=False)

    # 2) Full keyword universe — basic momentum/burst/growth (no MK).
    full_rows: list[dict] = []
    full = Path("data/analysis/keyword_trends.csv")
    if full.exists():
        with full.open(encoding="utf-8") as f:
            full_rows = list(csv.DictReader(f))
        matches = _kw_match(full_rows, keyword)
        if matches:
            out = []
            for r in matches[:3]:
                try:
                    growth = float(r.get("growth_rate") or 0)
                except (TypeError, ValueError):
                    growth = 0.0
                direction = "rising" if growth > 0.05 else ("falling" if growth < -0.05 else "stable")
                out.append(
                    {
                        "关键词": r.get("keyword"),
                        "累计论文数": r.get("doc_count"),
                        "增长方向": _direction_cn(direction),
                        "统计依据": {
                            "阶段增长率": r.get("growth_rate"),
                            "近期活跃度分": r.get("momentum_score"),
                            "短期加速分": r.get("burst_score"),
                        },
                        "说明": "来自全量关键词趋势(非 top 热点,无 MK 检验);回答时翻译为自然语言。",
                    }
                )
            return json.dumps(out, ensure_ascii=False)

    # 3) Miss — offer indexed keywords sharing tokens so one retry can succeed.
    # Search both tables together: the best phrase match may only exist in one.
    suggestions = _suggest(hot_rows + full_rows, keyword)
    if suggestions:
        return (
            f"未找到与 '{keyword}' 匹配的趋势数据。已收录的相近关键词: "
            f"{json.dumps(suggestions, ensure_ascii=False)}。请从中选一个再调用 get_trends。"
        )
    return f"未找到与 '{keyword}' 匹配的趋势数据(可能不是被收录的关键词)。"


TOOL = Tool(
    name="get_trends",
    schema=SCHEMA,
    run=run,
    prompt_fragment="查某关键词/主题的研究趋势(增长方向、阶段、预测)",
)
