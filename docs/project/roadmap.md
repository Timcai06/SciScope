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

### 第 2 步 — 矛盾即资产

把检测到的立场/矛盾落库（新增 `claim_evidence_stance` / `contradictions` 表），
随语料增长自己生长——**这就是"活的知识体"的种子：一张科学争议地图。**

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
