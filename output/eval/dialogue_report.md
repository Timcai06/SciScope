# SciScope 对话质量回归评测

生成时间:2026-07-07T13:03:12.782328+00:00
通过:**7/7**

| 场景 | 结果 | 锚定的真实问题 | 耗时 | 字数 |
|---|---|---|---|---|
| reference-resolution | ✅ | 规划器看不到历史,生成了 get_paper(paper_id='2') | 25.6s | 464 |
| claim-honesty | ✅ | 反思层把「证据不足」逼成「明确支持」(确认偏误) | 36.8s | 1052 |
| trend-faithful | ✅ | get_trends 返回 falling,回答却写成增长阶段 | 20.9s | 1275 |
| boundary-2027 | ✅ | 语料时间边界(收录至 2026) | 16.7s | 246 |
| vague-question | ✅ | 模糊问题曾盲搜 8 次工具调用烧光预算 | 3.6s | 377 |
| common-sense | ✅ | 常识问题不必检索 | 5.7s | 709 |
| survey-discipline | ✅ | 综述回答 1700+ 字、旁白开头、结尾总结段 | 21.0s | 1142 |

---
*复现:`make eval-dialogue`(需 DeepSeek key + PostgreSQL + 本地 embedder;在线评测,不进 CI)。*