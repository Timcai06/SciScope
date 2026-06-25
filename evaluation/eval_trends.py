"""Backtest the trend forecast model: fit on 2022--2024, predict 2025, compare
to the actual 2025 normalized document frequency.

维护指标口径:
- 对每个关键词独立拟合 2022/2023/2024 的时间序列，并预测 2025.
- `MAE/RMSE`: 在所有被评估关键词上比较 `forecast_2025` 与 `normalized_df_2025`。
- `pearson_pred_vs_actual`: 预测与真实值的皮尔逊相关系数，用于衡量排名方向一致性而非绝对误差。
- `directional_accuracy`: `sign(预测-2024)` 与 `sign(真实-2024)` 一致比例，聚焦趋势方向而非幅度。
- `mae_improvement_vs_naive`: 与持平基线 (`2025 = 2024`) 的相对改进，`>0` 代表优于基线。
- `naive_persistence_mae`: 持平基线 MAE，供最小行为线做对照。

数据假设与边界:
- 读取 `data/analysis/keyword_trends.csv`；仅保留 `doc_count >= min_doc_count` 且非噪声关键词（`is_noise_keyword`）。
- 归一化文档频率列必须包含 `normalized_df_YYYY`。
- 结果反映离线回测样本集合，不应直接外推为未来真实业务预测置信区间；无置信区间时不报告。
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.models.keyword_filter import is_noise_keyword
from src.models.trends import _fit_forecast

ANALYSIS_DIR = Path("data/analysis")
MIN_DOC_COUNT = 30


def run(analysis_dir: Path = ANALYSIS_DIR, min_doc_count: int = MIN_DOC_COUNT) -> dict:
    df = pd.read_csv(analysis_dir / "keyword_trends.csv")
    df = df[df["doc_count"] >= min_doc_count].copy()
    df = df[~df["keyword"].astype(str).map(is_noise_keyword)].copy()

    train_years = np.array([2022.0, 2023.0, 2024.0])
    preds, actuals, prev = [], [], []
    for _, row in df.iterrows():
        y = np.array([float(row.get(f"normalized_df_{yr}", 0.0) or 0.0) for yr in (2022, 2023, 2024)])
        actual_2025 = float(row.get("normalized_df_2025", 0.0) or 0.0)
        fc = _fit_forecast(train_years, y)  # predicts next year = 2025
        preds.append(max(0.0, fc["forecast"]))
        actuals.append(actual_2025)
        prev.append(y[-1])  # 2024 value, for directional comparison
    # 逐行循环在关键词维度独立计算指标；当某关键词序列异常时以 0 填充，可复现性优先于强制清洗。

    preds, actuals, prev = np.array(preds), np.array(actuals), np.array(prev)
    n = len(preds)
    err = preds - actuals
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    # Pearson correlation between predicted and actual
    if preds.std() > 0 and actuals.std() > 0:
        pearson = float(np.corrcoef(preds, actuals)[0, 1])
    else:
        pearson = 0.0
    # Directional accuracy: sign(pred-2024) vs sign(actual-2024)
    pred_dir = np.sign(preds - prev)
    actual_dir = np.sign(actuals - prev)
    directional = float(np.mean(pred_dir == actual_dir))
    # baseline: naive "next = last" (persistence)
    naive_mae = float(np.mean(np.abs(prev - actuals)))

    return {
        "keywords_evaluated": int(n),
        "train_years": [2022, 2023, 2024],
        "target_year": 2025,
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "naive_persistence_mae": round(naive_mae, 6),
        "mae_improvement_vs_naive": round((naive_mae - mae) / naive_mae, 4) if naive_mae else 0.0,
        "pearson_pred_vs_actual": round(pearson, 4),
        "directional_accuracy": round(directional, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest trend forecast (2022-2024 -> 2025)")
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--min-doc-count", type=int, default=MIN_DOC_COUNT)
    args = parser.parse_args()
    print(json.dumps(run(args.analysis_dir, args.min_doc_count), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
