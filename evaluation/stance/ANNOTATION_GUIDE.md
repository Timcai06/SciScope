# SciScope Gold v1 标注指南

## 目标与边界

每条样本只判断给定 `evidence` 对给定 `claim` 的关系，不能用领域常识、论文标题或未提供上下文补足。正式集至少 80 条，必须有中、英、跨语三个语言层；双人独立标注，第三位领域专家只裁决分歧。

`dev_fixture.jsonl` 只是脚本回归样例，**不得**复制、改写或计入 Gold v1。

## 标签

- `SUPPORT`：证据中的明确陈述支持该 claim；必须摘出逐字出现的 `evidence_sentence`。
- `CONTRADICT`：证据明确表示 claim 的方向、数值或条件不成立；同样必须给出逐字证据句。
- `NEUTRAL`：只谈同一主题、信息不足、不能区分因果与关联，或没有足以判断的原句；证据句留空。

“未观察到显著效应”不等于“证明没有效应”；相关性不等于因果；研究背景陈述不等于作者的实验结论。

## 限定条件

只要研究对象、物种、人群、剂量、时间窗、任务定义或结局指标与 claim 的隐含范围不匹配，就在 `qualification` 说明差异。例如“体外细胞，不能直接外推患者”。这类记录可以保留其局部 stance，但不得作为一般性 claim 的可采信证据。

## 运行流程

1. 准备无标签 `candidates.jsonl`：每条含 `id, claim, evidence, language, source`。
2. `python -m evaluation.build_stance_packets --candidates ... --out-dir ...` 创建两个打乱顺序的 packet 和哈希清单。
3. 两位标注者各自填写 `stance, evidence_sentence, qualification, notes`，不得互看。
4. `python -m evaluation.reconcile_stance_annotations ...` 输出双标一致项与裁决队列。
5. 专家填写队列中的 `adjudicated_*` 字段；最终集须通过 `finalise_gold` 校验后冻结、哈希，并且从训练/调参中排除。
