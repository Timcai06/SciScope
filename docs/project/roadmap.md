# SciScope 目标与路线图（Roadmap）

> 方针（"为什么"）见 [charter.md](charter.md)。本文件是"往哪走、下一步动哪"。
> 每一步都锚定同一个北极星：**把 `[n]` 从"相关"升级为"蕴含/矛盾"。**

## 状态基线（2026-07）

- 竞赛交付：**已完成并冻结**（数据分析报告 + 项目报告书 + 可复现代码/模型/评测）。
  交付存档见 [../reports/](../reports/) 与根目录 `交付说明.md`。
- 数据层：已建齐并评测，**不再扩语料**（见 charter「数据方针」）。
- 现在进入**产品演进期**：从"竞赛交付物"转向"活的科学证据层"。

## 目标分层

| 层 | 目标 | 兑现的方针 |
|---|---|---|
| **近（现在起）** | 修好证据接地的裂缝：`verify_claim` 能分清"支持 vs 反驳" | 证据接地是魂 |
| **中** | 矛盾沉淀成会生长的"科学争议地图"；MCP 成为正门 | 活的知识体 / 证据后端 |
| **远** | 主动预警争议前线、假说引擎、被其他 agent 广泛调用 | 全部三条方针 |

## 落地路线（从明天能动的第一步开始）

### 第 0 步 — 先证明缺陷（证据优先）✅ 已完成

写了一个 `xfail(strict=True)` 测试：喂 `verify_claim` 一句论断和它的否定，断言两者
不该同判。当时两者都判"强支持"，缺陷被钉住。

- 落点：`backend/tests/test_verify_claim_stance.py`
- 缺陷位置：`backend/app/agent/tools/verify_claim.py`（纯余弦判 verdict）

### 第 1 步 — 给 verify_claim 加 stance 层 ✅ 已完成

对检索到的每条证据，用 LLM judge 判定 **支持 / 反驳 / 中立**（`SUPPORT/CONTRADICT/
NEUTRAL`）。verdict 由立场标签聚合，新增 `证据反驳`、`存在争议` 两档与 `证据立场统计`；
judge 不可用时回退到相似度旧判定（`判定方式=similarity`）。

- 落点：`backend/app/agent/tools/verify_claim.py` 的 `_judge_stances()` + `run()`
- 结果：一句论断与它的反面得到不同结论（强支持 vs 证据反驳）；全套测试 229 passed
- 效果：SciScope 成为会告诉你"文献里有人反对"的科研 agent

### 插曲 — 产品力打磨(2026-07,进行中)

第 2 步暂缓,先全维度提升现有产品的对话质量(对照 Claude Code 源码的做法):

**第一批(提示层)**:系统提示补齐日期与语料时间边界、引用规范(关键论断标注论文
标题+年份)、结论先行与如实报告约束;autocompact 摘要器升级为结构化备忘(保留
paper_id、用户纠正、未完成项)。落点:`backend/app/agent/prompts.py`、`langgraph_runtime.py`。

**第三批(清尾)**:检索去重(同轮内不同 query 重复返回的论文压缩为提示,含
verify_claim 嵌套证据,落点 `tool_runner.py`);趋势关键词同义变体折叠(GNN 单复数
两行方向相反的自相矛盾,合并展示并标注冲突,落点 `tools/get_trends.py`);回答长度
纪律(小标题至多 3 个、禁结尾总结段、合成指令带 500 字锚点)。
**第四批(评测固化)**:新增 `evaluation/eval_dialogue.py`(`make eval-dialogue`)——
7 个场景、18 个检查点,每个锚定一次真实体验踩过的坑(指代消解、确认偏误、趋势忠实、
时间边界、模糊反问、常识直答、综述纪律),在线评测防提示词改动回归。首轮基线 4/7,
按失败项修复(旁白改确定性剥离 `_strip_narration`、超界年份不充数、出处必须含标题)
后 7/7。产物:`output/eval/dialogue_report.{json,md}`。

**关键回归修复**:自检/反思曾把「证据不足」的诚实结论当弱回答强制重试,逼模型改口
"明确支持"(确认偏误,直接违背证据接地方针)。现在有引用的诚实判定(证据不足/证据
反驳/存在争议)不再触发重试,审稿提示明确「严禁因为回答没有证实用户的说法而要求重试」。
实测:求证类问题 0 次强制重试,证据不足结论站住,回答 1075→571 字。

**第二批(体验驱动)**:用真实 provider 亲测 5 会话 11 轮对话,按暴露的问题修复:
规划器带上一轮回答做指代消解(「第 2 篇论文」不再编 paper_id);get_trends 归一化
匹配(连字符不再脱靶)+ 未命中时给相近已收录关键词 + 方向中文化(falling(下降))+
Mann-Kendall 显著性直出(p 不显著时提示不要下强结论);自检审稿标准对齐产品引用
格式(不再索要 DOI/卷期);系统提示禁过渡旁白、模糊问题先反问。复测 4 场景验证通过。
落点:`planning.py`、`reflection.py`、`tools/get_trends.py`、`prompts.py`。

### 第 2 步 — 矛盾即资产 ✅ 已完成

stance 判定成功的每次核查把全部已判定证据 upsert 到 `claim_evidence_stance` 表
（键 `(claim_norm, paper_id)`，复核刷新不累加）；`contradictions` 视图派生"同时有
支持与反驳"的论断——**争议地图的种子，随核查自己生长。**

- 落点：`infra/postgres/stance.sql`（表+视图，进 `make postgres-schema`）、
  `backend/app/services/stance_store.py`（fail-open 写入 + `disputed_claims()` 读取）、
  `verify_claim.py` 接入
- 边界：内部追加型资产沉淀，**不是模型可调用的写工具**；语料表不被触碰；
  数据库不可用时静默跳过、不影响回答（见 data-agent-boundary §六）
- 验证：真实链路 4 次核查落库 24 行；视图与改判语义经事务测试
  （正反各一票即入图、改判翻转不重复计数）

### 第 3 步 — 把 MCP server 扶正为正门

`backend/app/mcp_server.py` 现在是薄适配器。升级它：除 tools 外暴露 resources
（"当前争议前线"），让 `verify_claim` 成为别的 agent 调用的旗舰能力。
定位写进 README：**SciScope = 任意科研 agent 的证据后端。**

### 第 4 步 — 主动

后台 job 扫全语料，捞出高争议论断主动推送——"科学天气预报"的雏形。

## 每步兑现哪句愿景

| 步骤 | 改哪 | 兑现 |
|---|---|---|
| 0–1 | `verify_claim.py` | `[n]` 从相关→蕴含；认知免疫系统 |
| 2 | 新增表 | 活的知识体 / 争议前线 |
| 3 | `mcp_server.py` | 让别的 agent 来调用你 |
| 4 | 新增 job | 科学的天气预报 |

## 不做什么（同样重要）

- 不再扩语料、不堆已成熟的"检索/趋势/推荐"红海功能。
- 不重启 Web 前端作为主线（若做，按新范围单独立项）。
- 不把智能焊进任何界面；不做"又一个通用助手"。
