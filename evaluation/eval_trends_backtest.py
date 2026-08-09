"""G04a 趋势滚动回测：现有趋势逻辑 vs naive 基线，含描述性/预测边界判定。

设计（固定滚动时间切分，可重建）：
- 数据：``data/analysis/keyword_trends.csv`` 的 ``normalized_df_<year>`` 列；
  仅保留 ``doc_count >= min_doc_count`` 且非噪声关键词（与 ``eval_trends.py`` 同口径）。
- 切分：目标年 ``t ∈ {2024, 2025}``（**仅完整年份**；2026 是 YTD，不作为回测目标），
  训练窗口 ``[2022..t-1]``。每个切分只使用截至 ``t-1`` 的数据，不泄漏未来。
- 模型：
  - ``trend_model``：现有趋势逻辑（``src.models.trends._fit_forecast`` 的 damped
    Sen's-slope 外推，与线上 ``get_trends``/``hot_keywords.csv`` 同一函数）；
  - ``last_value``：朴素持平基线 pred = 最后观测值；
  - ``moving_average``：pred = 最近 2 年均值。
- 指标（每个切分 + 汇总）：样本数 n、时间窗口、MAE、sMAPE、Spearman（pred↔actual
  横截面秩相关）、方向 balanced accuracy（up/down 两类 recall 均值）。
- 边界判定：若 ``trend_model`` 未能在**多数切分点**的 MAE 与 sMAPE 上都严格优于最佳
  naive，或 Spearman 不显著（p>=0.05）→ ``descriptive_only=True``，输出与文档必须限定
  “描述性趋势”，不得称预测能力或研究方向结论。
- 失败案例：每个切分点 trend_model 绝对误差最大的前 ``top_failures`` 个关键词。
- 确定性：相同输入 → 相同输出（无随机量；numpy 运算为确定浮点）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models.keyword_filter import is_noise_keyword
from src.models.trends import _fit_forecast

ANALYSIS_DIR = Path("data/analysis")
MIN_DOC_COUNT = 30
# 完整年份序列（2026 为 YTD，不作为目标）。
ALL_YEARS = [2022, 2023, 2024, 2025, 2026]
# 目标年集合（完整年份），训练窗口为 [2022..t-1]。
TARGET_YEARS = [2024, 2025]
MA_WINDOW = 2


# --- 纯函数：切分与指标（可单测） ----------------------------------------------


def rolling_splits(target_years: list[int] | None = None, start_year: int = ALL_YEARS[0]) -> list[dict[str, Any]]:
    """固定滚动切分：target → train_years（train = [start..target-1]）。"""
    targets = target_years or TARGET_YEARS
    return [
        {"target_year": t, "train_years": list(range(start_year, t)), "window": f"{start_year}-{t - 1} → {t}"}
        for t in targets
        if t > start_year
    ]


def mae(actuals: np.ndarray, preds: np.ndarray) -> float:
    return float(np.mean(np.abs(preds - actuals)))


def smape(actuals: np.ndarray, preds: np.ndarray) -> float:
    if len(actuals) == 0:
        return 0.0
    denom = np.abs(actuals) + np.abs(preds)
    # 分母为 0（actual 与 pred 都为 0）的样本按 0 贡献处理，仍保留在全部 n 的
    # 平均分母中；不能通过 mask 把它们从样本量静默删掉。
    mask = denom > 0
    contributions = np.zeros(len(actuals), dtype=float)
    contributions[mask] = 2.0 * np.abs(preds[mask] - actuals[mask]) / denom[mask]
    return float(np.mean(contributions))


def _rank(values: np.ndarray) -> np.ndarray:
    """平均秩（tie 取均值），用于 Spearman 秩相关。"""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        ranks[order[i : j + 1]] = avg
        i = j + 1
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Spearman 秩相关（rho, p-value，双尾）。

    p 值用 Fisher z 变换 + 正态近似（``z = 0.5*ln((1+rho)/(1-rho))``，
    ``se = 1/sqrt(n-3)``），纯标准库实现，不引入 scipy 依赖；对横截面
    样本（n 通常数百以上）足够精确，结果确定。
    """
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    rx, ry = _rank(x), _rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return 0.0, 1.0
    rho = float(np.corrcoef(rx, ry)[0, 1])
    if abs(rho) >= 1.0:
        return rho, 0.0
    from math import erfc, log, sqrt

    z = 0.5 * log((1.0 + rho) / (1.0 - rho))
    se = 1.0 / sqrt(max(1, n - 3))
    p = float(erfc(abs(z) / se / sqrt(2.0)))
    return rho, min(1.0, p)


def _direction(actuals: np.ndarray, prevs: np.ndarray) -> np.ndarray:
    """方向：up / down / flat（相对上一观测）。"""
    d = np.sign(actuals - prevs)
    return np.where(d > 0, "up", np.where(d < 0, "down", "flat"))


def direction_balanced_accuracy(
    actuals: np.ndarray, prevs: np.ndarray, preds: np.ndarray
) -> tuple[float, float, float]:
    """方向 balanced accuracy（up/down 两类 recall 均值）+ 整体方向一致率。

    返回 (balanced_acc, overall_accuracy, flat_count)。flat 样本不参与 recall
    分母，但计入整体一致率（pred 方向也为 flat 才算对）。
    """
    actual_dir = _direction(actuals, prevs)
    pred_dir = _direction(preds, prevs)
    recalls = []
    for cls in ("up", "down"):
        mask = actual_dir == cls
        if mask.any():
            recalls.append(float(np.mean(pred_dir[mask] == cls)))
    balanced = float(np.mean(recalls)) if recalls else 0.0
    overall = float(np.mean(actual_dir == pred_dir))
    flat_count = int(np.sum(actual_dir == "flat"))
    return balanced, overall, flat_count


def decide_descriptive_only(split_metrics: list[dict[str, dict[str, float]]]) -> dict[str, Any]:
    """根据**未四舍五入**的逐切分指标决定是否禁止预测性表述。"""
    n_splits = len(split_metrics)
    required_majority = n_splits // 2 + 1
    mae_wins = sum(
        1
        for models in split_metrics
        if models["trend"]["mae"] < min(models["last"]["mae"], models["ma"]["mae"])
    )
    smape_wins = sum(
        1
        for models in split_metrics
        if models["trend"]["smape"] < min(models["last"]["smape"], models["ma"]["smape"])
    )
    spearman_significant = bool(split_metrics) and all(
        models["trend"]["spearman_p"] < 0.05 for models in split_metrics
    )
    descriptive_only = not (
        n_splits > 0
        and mae_wins >= required_majority
        and smape_wins >= required_majority
        and spearman_significant
    )
    return {
        "descriptive_only": descriptive_only,
        "reason": (
            f"mae_wins={mae_wins}/{n_splits},smape_wins={smape_wins}/{n_splits},"
            f"required_majority={required_majority},spearman_significant={spearman_significant}"
        ),
    }


# --- 回测主体 -----------------------------------------------------------------


def _series_for(row: pd.Series, years: list[int]) -> np.ndarray:
    return np.array([float(row.get(f"normalized_df_{yr}", 0.0) or 0.0) for yr in years])


def run_backtest(
    analysis_dir: Path = ANALYSIS_DIR,
    min_doc_count: int = MIN_DOC_COUNT,
    splits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    df = pd.read_csv(analysis_dir / "keyword_trends.csv")
    df = df[df["doc_count"] >= min_doc_count].copy()
    df = df[~df["keyword"].astype(str).map(is_noise_keyword)].copy()

    splits = splits or rolling_splits()
    split_results: list[dict[str, Any]] = []
    decision_metrics: list[dict[str, dict[str, float]]] = []
    all_failures: list[dict[str, Any]] = []

    for split in splits:
        target = split["target_year"]
        train_years = split["train_years"]
        rows: dict[str, list[float]] = {"trend": [], "last": [], "ma": []}
        actuals: list[float] = []
        prevs: list[float] = []
        per_kw_err: list[tuple[str, float, float, float]] = []

        train_arr = np.array([float(y) for y in train_years])
        for _, row in df.iterrows():
            kw = str(row.get("keyword") or "")
            train_values = _series_for(row, train_years)
            actual = float(row.get(f"normalized_df_{target}", 0.0) or 0.0)
            prev = float(train_values[-1]) if len(train_values) else 0.0

            fc = _fit_forecast(train_arr, train_values)
            trend_pred = max(0.0, fc["forecast"])
            last_pred = prev
            ma_pred = float(np.mean(train_values[-MA_WINDOW:])) if len(train_values) >= MA_WINDOW else prev

            rows["trend"].append(trend_pred)
            rows["last"].append(last_pred)
            rows["ma"].append(ma_pred)
            actuals.append(actual)
            prevs.append(prev)
            per_kw_err.append((kw, abs(trend_pred - actual), actual, trend_pred))

        actuals_arr = np.array(actuals)
        prevs_arr = np.array(prevs)
        n = len(actuals_arr)
        if n == 0:
            split_results.append(
                {"target_year": target, "train_years": train_years, "window": split["window"],
                 "n": 0, "note": "no_keywords_qualified"}
            )
            continue

        raw_models: dict[str, dict[str, float]] = {}
        per_model: dict[str, Any] = {}
        for name in ("trend", "last", "ma"):
            preds = np.array(rows[name])
            rho, p = spearman(preds, actuals_arr)
            balanced, overall, flat_count = direction_balanced_accuracy(actuals_arr, prevs_arr, preds)
            raw_models[name] = {
                "mae": mae(actuals_arr, preds),
                "smape": smape(actuals_arr, preds),
                "spearman_rho": rho,
                "spearman_p": p,
                "direction_balanced_acc": balanced,
                "direction_overall_acc": overall,
            }
            per_model[name] = {
                "mae": round(raw_models[name]["mae"], 6),
                "smape": round(raw_models[name]["smape"], 6),
                "spearman_rho": round(raw_models[name]["spearman_rho"], 4),
                "spearman_p": round(raw_models[name]["spearman_p"], 4),
                "direction_balanced_acc": round(raw_models[name]["direction_balanced_acc"], 4),
                "direction_overall_acc": round(raw_models[name]["direction_overall_acc"], 4),
            }

        # 失败案例：trend_model 绝对误差 top-K。
        per_kw_err.sort(key=lambda item: item[1], reverse=True)
        failures = [
            {"keyword": kw, "abs_error": round(err, 6), "actual": round(actual, 6), "pred": round(pred, 6)}
            for kw, err, actual, pred in per_kw_err[:5]
        ]
        all_failures.append({"target_year": target, "failures": failures})
        decision_metrics.append(raw_models)

        split_results.append(
            {
                "target_year": target,
                "train_years": train_years,
                "window": split["window"],
                "n": n,
                "models": per_model,
                "best_mae_model": min(raw_models, key=lambda m: raw_models[m]["mae"]),
                "best_smape_model": min(raw_models, key=lambda m: raw_models[m]["smape"]),
            }
        )

    # 描述性/预测边界判定：现有趋势逻辑须在多数切分点的 MAE 与 sMAPE 都优于最佳 naive，
    # 且 Spearman 显著（p<0.05）。
    decision = decide_descriptive_only(decision_metrics)
    decision.update(
        {
        "policy": (
            "descriptive_only=True 时，趋势输出与文档只可称“描述性趋势”（统计描述历史方向/波动），"
            "不得称预测能力、不得给出研究方向预测结论；"
            "descriptive_only=False 才可保留受约束的短期方向辅助。"
        ),
        }
    )

    return {
        "eval": "G04a_trend_rolling_backtest",
        "schema_version": "trends-backtest/v1",
        "params": {
            "min_doc_count": min_doc_count,
            "ma_window": MA_WINDOW,
            "splits": [{"target_year": s["target_year"], "train_years": s["train_years"]} for s in splits],
            "data_file": str(analysis_dir / "keyword_trends.csv"),
        },
        "splits": split_results,
        "failures": all_failures,
        "decision": decision,
    }


def _format_md(result: dict[str, Any]) -> str:
    lines = [
        "# G04a 趋势滚动回测结果（可重建）",
        "",
        f"- 数据文件：`{result['params']['data_file']}`",
        f"- min_doc_count：{result['params']['min_doc_count']}；移动平均窗口：{result['params']['ma_window']}",
        "",
        "## 边界判定",
        "",
        f"- **描述性趋势**：{result['decision']['descriptive_only']}",
        f"- 判定依据：{result['decision']['reason']}",
        "",
        "## 各切分结果",
        "",
    ]
    for s in result["splits"]:
        if s.get("n", 0) == 0:
            lines.append(f"- {s['window']}：n=0（无合格关键词）")
            continue
        lines.append(f"- **{s['window']}**：n={s['n']}")
        for name in ("trend", "last", "ma"):
            m = s["models"][name]
            lines.append(
                f"  - {name}: MAE={m['mae']}, sMAPE={m['smape']}, "
                f"Spearman={m['spearman_rho']}(p={m['spearman_p']}), "
                f"dir-balacc={m['direction_balanced_acc']}"
            )
    lines += ["", "## 失败案例（trend_model 绝对误差 Top5）", ""]
    for f in result["failures"]:
        lines.append(f"- 目标 {f['target_year']}: " + ", ".join(
            f"{x['keyword']}(err={x['abs_error']})" for x in f["failures"]
        ))
    lines.append("")
    lines.append("> 说明：2026 为 YTD 不作为回测目标；所有切分只用截至目标年前一年的数据，无未来泄漏。")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="G04a 趋势滚动回测")
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--min-doc-count", type=int, default=MIN_DOC_COUNT)
    parser.add_argument("--output", type=Path, default=Path("output/eval/trends_backtest.json"))
    args = parser.parse_args()

    result = run_backtest(args.analysis_dir, args.min_doc_count)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out.with_suffix(".md")).write_text(_format_md(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
