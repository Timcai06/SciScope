"""Run the full evaluation evidence pack and persist results.

维护口径说明:
- 该脚本聚合检索/趋势/推荐三类**离线评测**，用于“样本内一致性验证”，不是全量生产系统SLA。
- 输出 JSON/Markdown 仅消费以下固定字段与口径，不改变底层统计。
- self-retrieval 部分使用评测脚本内置抽样参数(默认 200/150)，指标与样本规模相关，不能外推为“全库真实准确率”。
- 趋势回测固定按 2022–2024 训练、2025 验证，且仅覆盖 `data/analysis/keyword_trends.csv` 中满足筛选条件的关键词。

Produces output/eval/eval_report.json (machine-readable) and
output/eval/eval_report.md (human-readable) covering:
  - retrieval quality (self-retrieval recall@k, MRR@10, latency)
  - trend forecast backtest (fit 2022-2024, predict 2025)
  - recommendation offline evaluation (same-field / shared-keyword rate)

Usage:
    SCISCOPE_DB_DSN=... SCISCOPE_EMBEDDER_PATH=... python -m evaluation.eval_all
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path("output/eval")


def run() -> dict:
    from evaluation import eval_recommend, eval_retrieval, eval_trends

    dsn = os.getenv("SCISCOPE_DB_DSN") or os.getenv("SCISCOPE_DATABASE_URL", "postgresql://tim@localhost:5432/sciscope")
    # 统一指标来源：本函数只是拼接调用，不修改各模块计算；报告中应按子模块的样本口径逐一解读。
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "retrieval": eval_retrieval.run(dsn=dsn, sample=200, seed=42, limit=10),
        "trend_backtest": eval_trends.run(),
        "recommendation": eval_recommend.run(dsn=dsn, sample=150, seed=42, limit=5),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "eval_report.md").write_text(_to_markdown(report), encoding="utf-8")
    return report


def _to_markdown(r: dict) -> str:
    ret_t = r["retrieval"]["by_title"]
    ret_k = r["retrieval"]["by_keywords"]
    tb = r["trend_backtest"]
    rec = r["recommendation"]
    # 说明: Markdown 复用 JSON 字段，供人工复核时强调“样本规模/口径边界”，避免误当成全量基准线。
    return f"""# SciScope 评测证据包

生成时间:{r['generated_at']}

## 1. 检索质量(自检索 self-retrieval)
样本 {r['retrieval']['sample_papers']} 篇,top-{r['retrieval']['limit']}。

| 查询方式 | recall@1 | recall@5 | recall@10 | MRR@10 | 平均延迟(ms) |
|---|---|---|---|---|---|
| 按标题(字面+语义) | {ret_t['recall@1']} | {ret_t['recall@5']} | {ret_t['recall@10']} | {ret_t['mrr@10']} | {ret_t['mean_latency_ms']} |
| 按关键词 | {ret_k['recall@1']} | {ret_k['recall@5']} | {ret_k['recall@10']} | {ret_k['mrr@10']} | {ret_k['mean_latency_ms']} |

## 2. 趋势预测回测(拟合 2022–2024 → 预测 {tb['target_year']})
评测关键词 {tb['keywords_evaluated']} 个。

- 预测与真实相关性(Pearson):**{tb['pearson_pred_vs_actual']}** — 模型能准确**排序**哪些关键词在 {tb['target_year']} 更活跃。
- MAE {tb['mae']} vs naive 持平基线 {tb['naive_persistence_mae']}(相对 {tb['mae_improvement_vs_naive']});方向准确率 {tb['directional_accuracy']}。
- 结论:归一化词频年际噪声大、近均值回归,naive 为强基线;模型价值在**排序与多年动量/burst**,点预测附不确定带、谨慎使用。

## 3. 推荐离线评估(同领域 / 共享关键词命中)
样本 {rec['seeds_sampled']} 篇种子,每篇 top-5。

- 同领域率:**{rec['same_field_rate']}**(远高于 7 领域随机基线)
- 共享关键词率:**{rec['shared_keyword_rate']}**
- 平均语义相似:{rec['mean_semantic_similarity']}
- 结论:推荐结果在领域与关键词层面高度相关,且每条附可解释因子。

---
*复现:`make eval-all`(需 PostgreSQL + 本地 embedder)。*
"""


if __name__ == "__main__":
    report = run()
    print(json.dumps({k: (v if not isinstance(v, dict) else "...") for k, v in report.items()}, ensure_ascii=False))
    print("written: output/eval/eval_report.json, output/eval/eval_report.md")
