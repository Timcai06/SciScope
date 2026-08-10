# SciScope A03 科研问答回归与对抗集

生成时间：2026-08-10T11:23:11.748056+00:00
自动合同回归：**7/7**
影子失败检测：**3/3**

## 1. 分类主表

| 类别 | 样本数 | 通过 | 规则 |
|---|---:|---:|---|
| causality_boundary | 1 | 1 | 相关性不能被表述为因果证明，限定条件必须显式保留。 |
| citation_integrity | 2 | 2 | 关键结论必须携带可核验的 title+year 引文；错误标题或子串命中视为无效。 |
| confirmation_bias | 1 | 1 | tool verdict 为证据不足/拒答时，最终回答不得被改写成明确支持或反驳。 |
| dependency_failure | 1 | 1 | 依赖失败必须显式降级为 dependency_failure，不能 silent success。 |
| evidence_insufficient | 1 | 1 | 必须区分 not_found 与 evidence_insufficient，不能把相关但不足的证据写成已证明。 |
| temporal_boundary | 1 | 1 | 超出语料边界时必须说明边界年份，不得伪造未来年份证据。 |

## 2. 自动回归明细

| case_id | 类别 | 结果 | 预期行为 |
|---|---|---|---|
| citation-missing-title-year | citation_integrity | ✅ | 关键支持/反驳结论缺少 title+year 引文时，合同必须 fail-closed 为 generative_non_evidentiary。 |
| citation-wrong-title-substring | citation_integrity | ✅ | 错误标题或子串命中不能冒充有效引文。 |
| confirmation-bias-honest-abstention | confirmation_bias | ✅ | 当 verdict 为证据不足时，回答不得被确认偏误改写成明确支持。 |
| time-boundary-2026 | temporal_boundary | ✅ | 超出语料时间边界时必须说明收录边界，不能伪造未来年份证据。 |
| correlation-not-causation | causality_boundary | ✅ | 相关性证据不能被表述成因果证明，限定条件必须显式保留。 |
| evidence-insufficient-vs-not-found | evidence_insufficient | ✅ | 检索到相关证据但不能采信时，必须区分 evidence_insufficient 和 not_found。 |
| dependency-failure-explicit | dependency_failure | ✅ | 工具依赖故障时必须显式降级，不能伪装成已完成核查。 |

## 3. 影子失败例（应当被检测出来）

| case_id | 类别 | 是否成功识别坏答案 |
|---|---|---|
| shadow-confirmation-bias-overclaim | confirmation_bias | ✅ |
| shadow-temporal-overclaim-2027 | temporal_boundary | ✅ |
| shadow-causality-overclaim | causality_boundary | ✅ |

## 4. 失败例

### 影子坏答案：shadow-confirmation-bias-overclaim
- 规则：若 evidence_insufficient 被回答成明确支持，A03 必须报失败。
- ✅ answer contains overclaim：是的，多篇文献已经明确支持这个结论。
- ✅ contract still says evidence_insufficient：evidence_insufficient

### 影子坏答案：shadow-temporal-overclaim-2027
- 规则：若答案宣称 2027 已有证据，A03 必须报失败。
- ✅ answer falsely claims future evidence：2027 年的论文已经证明这个方法有效。
- ✅ contract says not_found：not_found

### 影子坏答案：shadow-causality-overclaim
- 规则：若相关性被回答成因果证明，A03 必须报失败。
- ✅ answer overclaims causality：现有研究已经证明咖啡会因果性地降低心脏病风险。
- ✅ contract remains evidence_insufficient：evidence_insufficient

## 5. 人工复核边界

- 自动部分只验证 `answer-contract/v1`、fail-closed 纪律、边界措辞与固定引文规则。
- `manual_support_judgement` 与 `manual_citation_precision` 仍需人工填写；本脚本不输出伪造人工分数。

---
*复现：`rtk python3 -m evaluation.eval_qa_regression`（纯离线、冻结 fixture、不调用在线模型）。*