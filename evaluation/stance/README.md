# SciScope stance evaluation

这里的评测资产区分三种证据等级，避免把开发样例包装成国家级效果：

- `dev_fixture.jsonl`：16 条中/英/跨语的**开发契约样例**，覆盖 support、contradict、neutral、限定条件和证据句。它用于离线回归及证明“相似度不能判反驳”，不是人工金标准，也不能用于申报效果数字。
- `scifact_anchor.json`：SciFact 外部英文锚点的版本/许可/逐文件哈希清单；官方原始数据须经 `scifact_eval` dry-run 准入。它是英文 gold 锚点，不是 SciScope 双语主表。
- `bilingual_silver_v0.jsonl` + `.manifest.json`：6 条**冻结的中文/跨语 silver**，逐条回链 SciFact dev 的官方 rationale。中文翻译和规则化反向论断均标作 `project_manual_unreviewed`；只用于回归或两个模型在同一冻结输入上的一致性，绝不是人工金标准。
- `gold_v1`（待建）：必须由双人独立标注、专家裁决、冻结 split 和可追溯来源构成；其真实规模与一致性指标达标后，才可用于国赛主表。

预测文件是一行一个 JSON 对象，至少包含 `id`、`stance`、`confidence`、`sentence`。运行：

```bash
python -m evaluation.eval_stance --baseline similarity
python -m evaluation.eval_stance --gold path/to/gold_v1.jsonl --predictions path/to/l3_predictions.jsonl
python -m evaluation.stance.silver_eval
python -m evaluation.stance.silver_eval --predictions-a model_a.jsonl --predictions-b model_b.jsonl --allow-agreement
```

输出包含 Macro-F1、各类 F1、证据句 exact match、非中立 coverage、Brier score 与 ECE。`similarity` 是刻意受限的字面相关度对照：它不产生 CONTRADICT，故不能替代 L3。

`silver_eval` 的默认模式只做冻结集、来源和 SciFact rationale 准入；agreement 模式只报告
`stance_agreement`、输入/预测哈希及语言分层，**不读取 silver 行的 `label` 进行评分**。因此它
不能输出 accuracy、校准指标或任何国赛主表数字。
