"""G04a 趋势滚动回测测试：切分构造、指标纯函数与描述性边界判定。

验收映射：
- 固定切分可重建（同一输入两次运行结果一致）；
- 每个指标有分母（n）与时间范围（window/train_years→target_year）；
- 指标计算正确（MAE/sMAPE/Spearman/方向 balanced accuracy 对已知数据）；
- 描述性/预测边界判定可由固定样例验证（trend 优于/劣于 naive 两种情形）。
"""

import json

import numpy as np
import pytest

from evaluation.eval_trends_backtest import (
    decide_descriptive_only,
    direction_balanced_accuracy,
    mae,
    rolling_splits,
    run_backtest,
    smape,
    spearman,
)


# --- 切分构造 ----------------------------------------------------------------


def test_rolling_splits_fixed_windows():
    splits = rolling_splits()
    assert [s["target_year"] for s in splits] == [2024, 2025]
    assert splits[0]["train_years"] == [2022, 2023]
    assert splits[1]["train_years"] == [2022, 2023, 2024]
    assert splits[0]["window"] == "2022-2023 → 2024"
    assert splits[1]["window"] == "2022-2024 → 2025"


def test_rolling_splits_never_leaks_future():
    for s in rolling_splits():
        assert s["target_year"] not in s["train_years"]
        assert max(s["train_years"]) < s["target_year"]


# --- 指标纯函数 ---------------------------------------------------------------


def test_mae_known_values():
    assert mae(np.array([1.0, 2.0]), np.array([1.5, 2.5])) == pytest.approx(0.5)
    assert mae(np.array([1.0, 2.0]), np.array([1.0, 2.0])) == 0.0


def test_smape_known_values():
    assert smape(np.array([1.0]), np.array([2.0])) == pytest.approx(2.0 / 3.0)
    # 分母为 0 的样本按 0 贡献，不除零。
    assert smape(np.array([0.0]), np.array([0.0])) == 0.0
    # 零值样本仍进入全部 n 的平均分母：贡献为 0，而不是被静默移除。
    assert smape(np.array([0.0, 1.0]), np.array([0.0, 2.0])) == pytest.approx(1.0 / 3.0)


def test_spearman_monotone_and_reverse():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    rho_up, p_up = spearman(x, np.array([1.5, 2.5, 3.5, 4.5]))
    assert rho_up == pytest.approx(1.0)
    rho_down, p_down = spearman(x, np.array([4.0, 3.0, 2.0, 1.0]))
    assert rho_down == pytest.approx(-1.0)
    assert p_down == pytest.approx(0.0)


def test_spearman_insufficient_samples():
    rho, p = spearman(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
    assert (rho, p) == (0.0, 1.0)


def test_direction_balanced_accuracy_known_case():
    # actual: up,up,down,down ; prev: 全为 10
    actuals = np.array([11.0, 12.0, 9.0, 8.0])
    prevs = np.array([10.0, 10.0, 10.0, 10.0])
    preds_perfect = np.array([11.0, 12.0, 9.0, 8.0])
    balanced, overall, flat_count = direction_balanced_accuracy(actuals, prevs, preds_perfect)
    assert balanced == pytest.approx(1.0)
    assert overall == pytest.approx(1.0)
    assert flat_count == 0
    # 全错：方向反转。
    preds_wrong = np.array([9.0, 8.0, 11.0, 12.0])
    balanced, _, _ = direction_balanced_accuracy(actuals, prevs, preds_wrong)
    assert balanced == pytest.approx(0.0)


# --- 回测主体与可重建性 ---------------------------------------------------------


def _small_csv(tmp_path, n_keywords: int = 5) -> object:
    import pandas as pd

    rng = np.random.default_rng(42)
    rows = []
    for i in range(n_keywords):
        base = float(0.001 + 0.0001 * i)
        vals = [base * (1 + 0.1 * k) for k in range(5)]  # 5 年,单调微升
        rows.append(
            {
                "keyword": f"kw{i}",
                "doc_count": 50 + i,
                "normalized_df_2022": vals[0],
                "normalized_df_2023": vals[1],
                "normalized_df_2024": vals[2],
                "normalized_df_2025": vals[3],
                "normalized_df_2026": vals[4],
            }
        )
    path = tmp_path / "keyword_trends.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_run_backtest_deterministic_and_complete(tmp_path):
    csv_path = _small_csv(tmp_path)
    r1 = run_backtest(tmp_path, min_doc_count=30)
    r2 = run_backtest(tmp_path, min_doc_count=30)
    assert r1 == r2  # 可重建：同输入同输出
    assert r1["eval"] == "G04a_trend_rolling_backtest"
    assert r1["schema_version"] == "trends-backtest/v1"

    for s in r1["splits"]:
        assert s["n"] == 5  # 分母明确
        assert s["window"]  # 时间范围明确
        for name in ("trend", "last", "ma"):
            m = s["models"][name]
            for key in ("mae", "smape", "spearman_rho", "spearman_p", "direction_balanced_acc"):
                assert key in m
    assert "decision" in r1 and "descriptive_only" in r1["decision"]
    assert len(r1["failures"]) == len(r1["splits"])


def test_run_backtest_json_serializable(tmp_path):
    import json as _json

    _small_csv(tmp_path)
    r = run_backtest(tmp_path, min_doc_count=30)
    dumped = _json.dumps(r, ensure_ascii=False)
    assert _json.loads(dumped) == r  # 全部可序列化


# --- 描述性/预测边界判定 --------------------------------------------------------


def test_descriptive_decision_true_when_trend_loses_to_naive(tmp_path):
    # 构造 trend 劣于 naive：随机波动序列,外推斜率必然放大误差。
    import pandas as pd

    rows = []
    for i in range(8):
        vals = [0.001, 0.002, 0.0009, 0.0021, 0.001]
        rows.append({"keyword": f"kw{i}", "doc_count": 100,
                     **{f"normalized_df_{y}": v for y, v in zip(range(2022, 2027), vals)}})
    path = tmp_path / "keyword_trends.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    r = run_backtest(tmp_path, min_doc_count=30)
    assert r["decision"]["descriptive_only"] is True
    assert "mae_wins=0/2" in r["decision"]["reason"] or "smape_wins=0/2" in r["decision"]["reason"]


def test_descriptive_decision_false_when_trend_beats_naive(tmp_path):
    # 构造 trend 优于 naive：持续单调强上升序列,Sen 斜率外推应优于持平；
    # 各关键词 base 不同,使横截面 Spearman 有变异（否则 rho 恒 0、p=1）。
    import pandas as pd

    rows = []
    for i in range(8):
        base = 0.0001 * (1 + 0.1 * i)
        vals = [base * (2 ** k) for k in range(5)]  # 指数式上升,水平各不同
        rows.append({"keyword": f"kw{i}", "doc_count": 100,
                     **{f"normalized_df_{y}": v for y, v in zip(range(2022, 2027), vals)}})
    path = tmp_path / "keyword_trends.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    r = run_backtest(tmp_path, min_doc_count=30)
    assert r["decision"]["descriptive_only"] is False
    assert "spearman_significant=True" in r["decision"]["reason"]


def test_two_splits_with_only_one_win_are_not_a_majority():
    # 两个切分只有一个胜出不是“多数”，必须继续保持描述性模式。
    win = {
        name: {"mae": value, "smape": value, "spearman_p": 0.01}
        for name, value in (("trend", 0.10), ("last", 0.20), ("ma", 0.30))
    }
    loss = {
        name: {"mae": value, "smape": value, "spearman_p": 0.01}
        for name, value in (("trend", 0.30), ("last", 0.10), ("ma", 0.20))
    }
    decision = decide_descriptive_only([win, loss])
    assert decision["descriptive_only"] is True
    assert "required_majority=2" in decision["reason"]


def test_decision_uses_raw_metrics_not_display_rounding():
    # trend 的原始 MAE 更小，即使二者展示为同样的 6 位小数，也应算作严格胜出。
    split = {
        "trend": {"mae": 0.0003844, "smape": 0.0003844, "spearman_p": 0.01},
        "last": {"mae": 0.0003846, "smape": 0.0003846, "spearman_p": 0.01},
        "ma": {"mae": 0.0005000, "smape": 0.0005000, "spearman_p": 0.01},
    }
    decision = decide_descriptive_only([split])
    assert decision["descriptive_only"] is False
    assert "mae_wins=1/1" in decision["reason"]
