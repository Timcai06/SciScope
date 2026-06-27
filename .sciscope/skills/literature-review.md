---
name: literature-review
description: 围绕一个主题生成文献综述和研究现状
tools: search_literature, summarize_field, get_trends, query_knowledge_graph
---

你正在执行 SciScope 技能: 文献综述。

研究主题:
{{input}}

工作要求:
- 先使用 search_literature 或 summarize_field 获取代表性论文证据。
- 如用户关心发展方向,使用 get_trends 补充趋势判断。
- 如用户关心作者、关键词或主题关系,使用 query_knowledge_graph 补充结构信息。
- 按主题综合归纳,不要逐篇论文流水账复述。
- 论文只作为证据例子或出处补充,除非用户明确要求分析单篇论文。
- 证据不足时如实说明检索范围和缺口。

回答格式:
1. 研究现状
2. 主要方向
3. 代表性证据
4. 趋势与机会
5. 局限说明
