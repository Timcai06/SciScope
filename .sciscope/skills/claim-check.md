---
name: claim-check
description: 核查一个科研论断是否有文献证据支持
tools: verify_claim, search_literature
---

你正在执行 SciScope 技能: 论断核查。

输入论断:
{{input}}

工作要求:
- 第一动作必须调用 verify_claim 核查论断的文献接地情况;未看到工具结果前不要输出结论。
- 如 verify_claim 返回证据不足或需要补充出处,最多再使用一次 search_literature 检索相关论文。
- 输出支持等级、关键证据、证据边界和更谨慎的改写表述。
- 不要把“有相关论文”夸大成“结论已被完全证明”。
- 不要编造论文、paper_id、作者、年份或相似度。
- 默认 1 次工具调用即可;证据不足时最多 2 次。

回答格式:
1. 结论
2. 关键证据
3. 证据边界
4. 建议表述
