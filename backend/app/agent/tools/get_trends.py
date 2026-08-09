"""get_trends — research-trend evidence for a keyword/topic."""

from __future__ import annotations

import csv
import json
import os
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

_BACKTEST_SCHEMA_VERSION = "trends-backtest/v1"
_DEFAULT_BACKTEST_PATH = Path("output/eval/trends_backtest.json")


def _forecast_policy(path: Path | None = None) -> dict[str, Any]:
    """读取 G04a 的趋势边界判定；缺失或无效产物一律 fail-closed。

    产品不应只依赖自然语言提示来抑制预测性表述：评测未通过、评测产物缺失或契约不匹配时，
    直接禁止对外输出 forecast 数值。
    """
    candidate = path or Path(os.environ.get("SCISCOPE_TRENDS_BACKTEST_PATH", _DEFAULT_BACKTEST_PATH))
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "descriptive_only": True,
            "source": str(candidate),
            "reason": "trend_backtest_unavailable_fail_closed",
        }
    if payload.get("schema_version") != _BACKTEST_SCHEMA_VERSION:
        return {
            "descriptive_only": True,
            "source": str(candidate),
            "reason": "trend_backtest_schema_invalid_fail_closed",
        }
    decision = payload.get("decision")
    if not isinstance(decision, dict) or not isinstance(decision.get("descriptive_only"), bool):
        return {
            "descriptive_only": True,
            "source": str(candidate),
            "reason": "trend_backtest_decision_invalid_fail_closed",
        }
    return {
        "descriptive_only": decision["descriptive_only"],
        "source": str(candidate),
        "reason": str(decision.get("reason") or "trend_backtest_decision"),
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


def _file_data_version(path: Path) -> dict[str, Any]:
    """数据版本：文件 mtime + size（=分析产物构建时间戳，可审计、轻量、确定）。"""
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "present": False}
    from datetime import datetime, timezone

    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return {"path": str(path), "present": True, "mtime": mtime, "size": stat.st_size}


def _time_range_from_header(path: Path) -> dict[str, Any] | None:
    """从 CSV 表头推导统计年份窗口：``normalized_df_<year>`` 列 min..max。

    返回值带 ``source`` 字段（该时间范围来自哪个文件），避免多输入混源。
    YTD 判定纯由内容驱动：存在 ``ytd_<max>_normalized_df`` 列即标注
    ``2026 为 YTD``，不依赖系统时钟，保证确定性。
    """
    try:
        with path.open(encoding="utf-8") as handle:
            header = handle.readline().strip()
    except OSError:
        return None
    import re

    years = sorted(
        int(m.group(1))
        for m in re.finditer(r"normalized_df_(\d{4})", header)
    )
    if not years:
        return None
    lo, hi = years[0], years[-1]
    ytd = f"ytd_{hi}_normalized_df" in header
    return {
        "range": f"{lo}-{hi}",
        "ytd": ytd,
        "label": f"{lo}-{hi}({hi} YTD)" if ytd else f"{lo}-{hi}",
        "source": str(path),
    }


def _trend_envelope(
    *,
    status: str,
    keyword: str,
    results: Any,
    source_path: Path | None = None,
    extra_inputs: list[Path] | None = None,
    time_range: dict[str, Any] | None = None,
    unavailable_reason: str | None = None,
    extra_note: str | None = None,
    forecast_policy: dict[str, Any] | None = None,
) -> str:
    """统一查询解释信封：status / query / data_source / asset / results / note。

    版本 provenance 不混源：``asset.data_versions`` 记录**全部**输入文件各自的
    mtime/size；``asset.time_range`` 带 ``source`` 字段标明年份窗口来自哪个文件。
    """
    asset = None
    if source_path is not None:
        inputs = [source_path] + (extra_inputs or [])
        asset = {
            "data_versions": [_file_data_version(p) for p in inputs],
            "time_range": time_range or _time_range_from_header(source_path),
        }
    policy = forecast_policy or _forecast_policy()
    forecast_note = (
        "G04a 回测未通过或不可用，当前仅提供历史统计描述；不提供未来数值预测或研究方向预测。"
        if policy["descriptive_only"]
        else "G04a 回测满足当前门槛；预测仍是历史年份列的受约束外推，不构成确定性结论。"
    )
    note = (
        "趋势基于统计口径 normalized_df_<year>（时间范围见 asset.time_range）；"
        "方向与显著性为统计描述；"
        f"{forecast_note}"
    )
    if extra_note:
        note = f"{note} {extra_note}"
    return json.dumps(
        {
            "status": status,
            "query": {"kind": "trend", "keyword": keyword},
            "data_source": "trend_assets" if source_path is not None else None,
            "asset": asset,
            "trend_policy": policy,
            "results": results,
            "unavailable_reason": unavailable_reason,
            "note": note,
        },
        ensure_ascii=False,
    )


def run(args: dict[str, Any]) -> str:
    keyword = str(args.get("keyword") or "").strip().lower()
    if not keyword:
        return _trend_envelope(status="empty", keyword=keyword, results=[], unavailable_reason="keyword_empty")

    hot_rows: list[dict] = []
    full_rows: list[dict] = []
    forecast_policy = _forecast_policy()
    hot = Path("models/trends/hot_keywords.csv")
    full = Path("data/analysis/keyword_trends.csv")

    # 依赖缺失：两个趋势数据文件都不存在 → 结构化 unavailable（不抛异常）。
    if not hot.exists() and not full.exists():
        return _trend_envelope(
            status="unavailable",
            keyword=keyword,
            results=[],
            unavailable_reason="trend_data_unavailable",
            extra_note="趋势数据文件缺失（models/trends/*.csv 与 data/analysis/keyword_trends.csv 均不存在）。",
        )

    # 1) Top-tracked keywords — full stats incl. Mann-Kendall / Sen's slope.
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
                    "生命周期阶段": rep.get("lifecycle_stage"),
                    "回答提示": "请说明历史趋势方向与统计依据；趋势不显著或样本小时，如实说明方向不可靠。",
                }
                if not forecast_policy["descriptive_only"]:
                    item["预测目标年份(受约束外推)"] = rep.get("forecast_next_year")
                    item["该年外推归一化词频"] = rep.get("forecast_normalized_df")
                if variants:
                    item["同义变体"] = variants
                if conflicting:
                    item["变体提醒"] = (
                        "该关键词的同义变体各自统计出的方向不一致(样本小、均不可靠),"
                        "不要据此断言趋势方向,应以论文数更多的行为主并说明不确定性。"
                    )
                out.append(item)
            return _trend_envelope(
                status="ok", keyword=keyword, results=out,
                source_path=hot,
                extra_inputs=[full] if full.exists() else [],
                time_range=_time_range_from_header(full) or _time_range_from_header(hot),
                forecast_policy=forecast_policy,
            )

    # 2) Full keyword universe — basic momentum/burst/growth (no MK).
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
            return _trend_envelope(
                status="ok", keyword=keyword, results=out,
                source_path=full, time_range=_time_range_from_header(full), forecast_policy=forecast_policy,
            )

    # 3) Miss — offer indexed keywords sharing tokens so one retry can succeed.
    suggestions = _suggest(hot_rows + full_rows, keyword)
    if suggestions:
        return _trend_envelope(
            status="empty",
            keyword=keyword,
            results=[],
            unavailable_reason=None,
            extra_note=f"未找到与 '{keyword}' 精确匹配的趋势数据;已收录相近关键词: "
                       f"{json.dumps(suggestions, ensure_ascii=False)}。可改用其中之一再查询。",
            forecast_policy=forecast_policy,
        )
    return _trend_envelope(
        status="empty",
        keyword=keyword,
        results=[],
        unavailable_reason=None,
        extra_note=f"未找到与 '{keyword}' 匹配的趋势数据(可能不是被收录的关键词)。",
        forecast_policy=forecast_policy,
    )


TOOL = Tool(
    name="get_trends",
    schema=SCHEMA,
    run=run,
    prompt_fragment="查某关键词/主题的历史统计趋势（增长方向、阶段与不确定性）",
)
