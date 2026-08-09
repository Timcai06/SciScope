# G04a 趋势滚动回测结果（可重建）

- 数据文件：`data/analysis/keyword_trends.csv`
- min_doc_count：30；移动平均窗口：2

## 边界判定

- **描述性趋势**：True
- 判定依据：mae_wins=0/2,smape_wins=0/2,required_majority=2,spearman_significant=True

## 各切分结果

- **2022-2023 → 2024**：n=1998
  - trend: MAE=0.000524, sMAPE=0.597925, Spearman=0.6926(p=0.0), dir-balacc=0.4351
  - last: MAE=0.000509, sMAPE=0.503432, Spearman=0.7332(p=0.0), dir-balacc=0.0
  - ma: MAE=0.000549, sMAPE=0.504339, Spearman=0.7277(p=0.0), dir-balacc=0.5604
- **2022-2024 → 2025**：n=1998
  - trend: MAE=0.000385, sMAPE=0.56123, Spearman=0.7428(p=0.0), dir-balacc=0.4166
  - last: MAE=0.000349, sMAPE=0.421348, Spearman=0.7915(p=0.0), dir-balacc=0.0
  - ma: MAE=0.000385, sMAPE=0.407677, Spearman=0.7791(p=0.0), dir-balacc=0.6011

## 失败案例（trend_model 绝对误差 Top5）

- 目标 2024: cond mat mtrl sci(err=0.037942), retrieval augmented generation(err=0.037781), cancer(err=0.034271), large language model(err=0.022572), task project management(err=0.012163)
- 目标 2025: cond mat mtrl sci(err=0.043185), cancer(err=0.036986), cond mat mes hall(err=0.010738), information retrieval(err=0.010586), natural language processing(err=0.00968)

> 说明：2026 为 YTD 不作为回测目标；所有切分只用截至目标年前一年的数据，无未来泄漏。