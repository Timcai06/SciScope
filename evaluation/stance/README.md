# SciScope stance evaluation

这里的评测资产区分三种证据等级，避免把开发样例包装成国家级效果：

- `dev_fixture.jsonl`：16 条中/英/跨语的**开发契约样例**，覆盖 support、contradict、neutral、限定条件和证据句。它用于离线回归及证明“相似度不能判反驳”，不是人工金标准，也不能用于申报效果数字。
- `scifact_anchor.json`：SciFact 外部英文锚点的版本/许可清单；当前只登记来源，尚未下载数据或报告结果。
- `gold_v1`（待建）：必须由双人独立标注、专家裁决、冻结 split 和可追溯来源构成；其真实规模与一致性指标达标后，才可用于国赛主表。

预测文件是一行一个 JSON 对象，至少包含 `id`、`stance`、`confidence`、`sentence`。运行：

```bash
python -m evaluation.eval_stance --baseline similarity
python -m evaluation.eval_stance --gold path/to/gold_v1.jsonl --predictions path/to/l3_predictions.jsonl
```

输出包含 Macro-F1、各类 F1、证据句 exact match、非中立 coverage、Brier score 与 ECE。`similarity` 是刻意受限的字面相关度对照：它不产生 CONTRADICT，故不能替代 L3。
