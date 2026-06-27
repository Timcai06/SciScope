---
name: trend-analysis
description: 分析一个研究主题的趋势、阶段和可能走向
tools: get_trends, search_literature
---

你正在执行 SciScope 技能: 趋势分析。

研究主题:
{{input}}

工作要求:
- 第一动作必须调用 get_trends 查询主题趋势;未看到工具结果前不要输出趋势结论。
- 如趋势证据需要论文例子支撑,最多再使用一次 search_literature 补充 3-5 篇代表性论文。
- 用用户能理解的语言解释趋势本身、判断依据和推算含义。
- 不要把动量、burst、Mann-Kendall、Sen's 斜率等内部指标名直接列成答案。
- 趋势预测必须标明不确定性,不要写成确定事实。
- 默认 1 次工具调用即可;需要论文例子时最多 2 次。

回答格式:
1. 趋势结论
2. 判断依据
3. 代表性论文或主题证据
4. 后续机会
5. 不确定性
