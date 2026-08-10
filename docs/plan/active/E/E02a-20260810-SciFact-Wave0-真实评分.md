# E02a｜SciFact Wave 0 真实评分（公开 dev）

> 状态：`REVISE`（有可复跑的官方格式本地 dev 分数；不满足 Wave 0 的 L3 门禁）
> 日期：2026-08-10
> 边界：本报告只报告 SciFact 官方公开数据和本次运行产物。它不把基线分数称为 L3，
> 不把 oracle 候选文档当成开放检索，也不把本地 dev 分数说成官方 test leaderboard。

## 结论

已实际生成预测并以 `--allow-score` 完成 SciFact 公开 dev 本地评分。分数为：

| 指标 | Precision | Recall | F1 |
|---|---:|---:|---:|
| abstract（标签正确且命中至少一组 rationale） | 0.269767 | 0.277512 | **0.273585** |
| sentence（完整 rationale 集约束） | 0.106977 | 0.188525 | **0.136499** |

样本为 300 个 dev claims、209 个 gold evidence abstracts、366 个 gold rationale sentences；
预测了 215 个 abstracts/645 个 sentences，命中 58/69。评分通过了原始数据 SHA256、schema 和引用
校验后才执行。由于该预测器的候选集合来自每条 claim 的 `cited_doc_ids`，它是 **oracle-candidate**
文档标签/证据句基线，不包含全 5,183 篇语料开放检索，不能代表端到端 SciScope 效果。

## 正确的预测 schema 与评分范围

官方格式是一条 claim 一行，而非旧的扁平 `{id, stance}`：

```json
{"id": 84, "evidence": {"22406695": {"label": "SUPPORT", "sentences": [1]}}}
```

每个 document evidence 只可预测 `SUPPORT` 或 `CONTRADICT`；`evidence: {}` 才表示
NEUTRAL。评分器拒绝缺失/重复 claim ID、未知 document、非法标签、越界 sentence，且要求
预测覆盖该 split 的全部 claim ID。它按官方公开规则计算：abstract 只有在 document、标签且至少一组
rationale 都命中时才正确；sentence 只有在完整 rationale 集被预测时才计入。

## 预测器与输入边界

- 模型：`tfidf-1to2-logreg-c1-min_df2-random_state0`（scikit-learn 的 TF-IDF 1–2gram +
  LogisticRegression；固定参数，无 dev 调参）。
- 训练：官方 `claims_train.jsonl` 的 809 claims / 919 cited-document pairs；标签由 train 的
  evidence 提取，分布为 SUPPORT 370、CONTRADICT 194、NEUTRAL 355。
- 预测：官方 dev 的 300 claims / 340 `cited_doc_ids` pairs。NEUTRAL 不写入官方 output；
  非中立文档的 rationale 是 claim 与 abstract sentence 的 lexical Jaccard 前 3 句。
- 实际环境：项目 Conda Python
  `/opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python`，其中观测到 `scikit-learn 1.8.0`。
  若依赖不存在，预测器 fail-closed，不会产生替代性伪预测。

## 复跑命令与产物

| 命令 | exit | 结果 |
|---|---:|---|
| `rtk /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python -m pytest backend/tests/test_scifact_admission.py -q` | 0 | 11 passed |
| `rtk /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python -m evaluation.stance.scifact_baseline --raw-dir data/scifact/raw --split dev --output output/eval/scifact_dev_tfidf_logreg_oracle_cited_v1.predictions.jsonl --report output/eval/scifact_dev_tfidf_logreg_oracle_cited_v1.generation.json` | 0 | 真实预测 JSONL + 生成记录 |
| `rtk /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python -m evaluation.stance.scifact_eval --raw-dir data/scifact/raw --split dev --predictions output/eval/scifact_dev_tfidf_logreg_oracle_cited_v1.predictions.jsonl --allow-score --output output/eval/scifact_dev_tfidf_logreg_oracle_cited_v1.score.json` | 0 | 真实本地 dev 评分 |

- [预测 JSONL](../../../../output/eval/scifact_dev_tfidf_logreg_oracle_cited_v1.predictions.jsonl)
- [生成记录](../../../../output/eval/scifact_dev_tfidf_logreg_oracle_cited_v1.generation.json)
- [评分报告（含失败案例）](../../../../output/eval/scifact_dev_tfidf_logreg_oracle_cited_v1.score.json)

## 已观察的失败例

评分报告固化了 3 个错误预测和 3 个漏掉的 gold abstracts。代表性问题：

- claim `5`（UK abnormal PrP positivity）：对 document `13734012` 预测为 CONTRADICT，
  gold 为 SUPPORT，且 top-3 lexical 句 `[3,7,2]` 漏掉 gold sentence `[4]`。
- claim `42`（alpha-thalassemia）：预测 SUPPORT，而两个 gold rationale 均为 CONTRADICT；
  有一组 gold rationale 需同时命中 `[1,9]`，简单三句词重叠选择未满足完整集约束。
- claim `3`（1000 Genomes rare variants）：gold SUPPORT document `14717500` 被预测为
  NEUTRAL（官方输出中为空 evidence），直接损失 abstract 与 sentence recall。

这些不是数据缺失或评分器降级，而是这个非 L3 基线在反驳识别和 rationale 定位上的真实失败。

## 门禁判定

SciFact **可执行真评分技术门禁已完成**，但 L3 质量门禁仍为 `REVISE`。已完成官方 schema、可重跑
预测、公开 dev 真实评分和失败可审计性；仍缺开放检索结果、受控 stance judge、校准/拒答、强证据句
选择器与独立双语 `gold_v1`。因此可以开展与质量主表分离的 E03 工程集成，但不得据此宣称 L3 达标。
