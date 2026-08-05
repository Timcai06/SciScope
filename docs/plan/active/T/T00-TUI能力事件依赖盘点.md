# T00｜TUI 能力、事件与运行依赖盘点（报告）

- 状态：`PASS`（只读盘点完成，验收待项目负责人复核）
- 领取时间：2026-08-05；负责人：Go TUI/演示负责人（T 线）
- 基线 SHA：`67e275a6d90dafb2b64ae261bb5932acd708a7bc`（分支 `main`）
- 预存改动（非本任务产生，未触碰）：`docs/plan/active/` 下 D/E/G 线的文档改动
  （`D-文献内容结构化.md`、`E-证据L3与国赛证明.md`、`README.md` 修改；
  `D/D00-数据准入清单.md`、`E/E00-基线与证据台账.md`、`G/G00-图谱推荐趋势基线.md` 新增）。
- 文件所有权：本文件 + T 线只读范围（`tui/`、SSE/OpenAPI 文档、golden session）。
  **未修改任何 Go/Python 代码。**
- 验证：`rtk go test ./...`（在 `tui/`）→ `Go test: 91 passed in 1 packages`，退出码 0。
- 在线状态（另列，见 §5）：本机后端（8000）与 LLM（8001）未启动，未做在线联调；
  数据库、图谱资产、本地会话均就绪。

## 1. 命令注册表（16 个 slash 命令，无幽灵命令）

来源：`tui/slash.go`（`slashCmds` 16 项 ↔ `slashExecutors` 16 项一一对应，
`buildSlashRegistry` 启动时校验，缺执行器即 registry 缺失）。

| 命令 | 类型 | 请求路径 / 本地行为 | 后端运行依赖 | 当前验证等级 |
|---|---|---|---|---|
| `/demo` | local | 播放固定脚本（`doctor_demo.go` `demoScriptMessages`），零依赖 | 无 | 单测 `TestDemoScriptCoversGoldenFlow`、`TestDemoModeReadsEnvironment` |
| `/verify <claim>` | prompt | 读 `.sciscope/skills/claim-check.md` → `POST /api/agent/stream` | 后端 Agent + LLM + 检索 + `verify_claim` | 单测 `TestPromptSlashCommandExpandsIntoAgentQuestion`、`TestSkillTemplateLoadsFromSciscopeDirectory` |
| `/review <topic>` | prompt | 读 `literature-review.md` → `POST /api/agent/stream` | 同上（`search_literature`/`summarize_field`/`get_trends`/`query_knowledge_graph`） | 单测同上（skill 模板机制）；模板本身未逐条断言 |
| `/trend <topic>` | prompt | 读 `trend-analysis.md` → `POST /api/agent/stream` | 同上（`get_trends` 优先） | 单测 `TestTrendSlashCommandUsesSkillTemplate` |
| `/recommend <topic\|paper_id>` | prompt | 读 `paper-recommendation.md` → `POST /api/agent/stream` | 同上（`recommend_papers` 依赖 `paper_embeddings`，当前缺失，见 §3） | 单测 `TestRecommendSlashCommandUsesSkillTemplate` |
| `/doctor` | ui | 本地检查：Backend `GET /readyz`、LLM `GET /v1/models`、Sessions 目录、Graph assets 路径 | 无（只读探测） | 单测 `TestDoctorReportRendersProductChecks`、`TestDoctorUsesReadinessAsBackendHealthCheck`、`TestBackendDoctorWarning` 等 |
| `/retry` | local | 重放 `lastQuestion` → `POST /api/agent/stream`（`retry=true`） | 同 `/verify` 类 | 单测 `TestRetrySlashReplaysLastQuestion` |
| `/export` | local | 写本地 Markdown（`writeSessionMarkdown`） | 无 | 单测 `TestExportMarkdownIncludesConversationAndEvidence`、`TestExportLastSessionReturnsNewestMarkdown` |
| `/sessions` | ui | 读会话目录（`SCISCOPE_SESSION_DIR` → `~/.sciscope/sessions` → `./sessions`） | 无 | 单测 `TestListSessionFilesReturnsNewestFirst`、`TestSessionsSlashRendersRecentSessions` |
| `/resume N` | ui | 读会话 Markdown 恢复 transcript | 无 | 单测 `TestLoadSessionMarkdownRestoresLastQuestion`、`TestSlashCommandOpensResumeSubmenuAndExecutesSelection` |
| `/timeline` | local | 渲染内存 timeline（来自本轮 SSE 事件） | 无（数据源自 SSE） | 单测 `TestTimelineSlashRendersCurrentTurnTrace`、`TestToolEventsStreamInlineAndAppearInTimeline` |
| `/tools` | ui | 展示静态工具目录（9 项，见 §2） | 无 | 单测 `TestSlashCommandOpensToolsDoctorAndConfirmSubmenus` |
| `/theme` | ui | 本地主题切换（dark/paper/light/contrast） | 无 | 单测 `TestThemeCommandListsAndSwitchesThemes`、`TestApplyThemeRejectsUnknownTheme` |
| `/help` | local | 渲染帮助块 | 无 | 单测 `TestHelpStringDocumentsHostedBackendDefault` |
| `/clear` | ui | 确认菜单后清空视图/历史/时间线 | 无 | 单测（submenu 机制覆盖） |
| `/quit` | ui | 确认菜单后退出 | 无 | 单测（submenu 机制覆盖） |

CLI 入口（非 slash）：`sciscope-tui [demo|doctor|export --last|--demo|--version|--help]`，
单测 `TestParseCLIOptions`、`TestVersionStringIncludesAppName`。

**结论**：16/16 命令有实现路径；prompt 类命令全部经唯一问答路径
`POST /api/agent/stream`，不承载解析/检索/推理（符合 T 线边界）。

## 2. 工具目录与后端注册表对照

TUI 静态目录（`tui/main.go` `toolCatalog`/`toolLabels`/`toolNamePattern`，9 项）：
`search_literature`、`get_trends`、`recommend_papers`、`get_paper`、
`summarize_field`、`compare_papers`、`export_bibliography`、
`query_knowledge_graph`、`verify_claim`。

后端 native 注册表（`backend/app/agent/tools/__init__.py` `NATIVE_TOOLS`，11 项）：
上述 9 项 + **`list_disputes`** + **`delegate`**。

| 差异 | 说明 | 影响 |
|---|---|---|
| TUI 目录缺 `list_disputes`（E 线争议读取工具） | 后端已注册；TUI 无图标/无目录项，`tool_result` 落通用卡（`panelRow("result", …)`） | 不阻塞展示（结果仍渲染）；T02 做争议卡时需补目录与语义高亮 |
| TUI 目录缺 `delegate`（专员子智能体） | 后端已注册；同上落通用卡 | 同上；无展示语义缺失以外的风险 |

**无幽灵命令**：TUI 列出的 9 个工具全部是后端真实注册工具（与 `NATIVE_TOOLS` 前 9 项完全一致），
无"目录里有但后端不存在"的工具。

## 3. SSE 事件消费清单

来源：`backend/app/agent/events.py`（`AgentEventType`）、`backend/app/api/routes_agent.py`（SSE 合同）、
`tui/stream.go`（消费侧）。

| 事件 type | 后端发出 | TUI 消费 | 渲染/落点 |
|---|---|---|---|
| `plan` | `langgraph_runtime` | `planMsg` → 研究计划块 + timeline + transcript | `main.go` `planMsg` |
| `text` | runtime | `textMsg` → 增量答案 | 实时 preview |
| `tool_call` | `_tool_call_event` | `toolCallMsg{name,args,meta}` → 调用行 + timeline + 权限提示 | `main.go` `toolCallMsg` |
| `tool_progress` | `_execute_tools`（`{name,message}`，2 元组无 meta） | **不消费**（无 switch 分支；meta 为空 → `nodePulseMsg` 判定 `metaEmpty` 直接忽略） | 无；进度随 `tool_result` 批到达（后端注释已说明需事件级流式才可实时） |
| `tool_result` | runtime | `toolResultMsg{name,result,meta}` → 结果卡（evidence/verify/trend/通用）+ transcript | `render.go` `renderToolResult` |
| `reflect` | runtime | `reflectMsg` → 自检修正块 | `main.go` `reflectMsg` |
| `final` | runtime | `finalMsg` → 研究结论块 | `main.go` `finalMsg` |
| `error` | `routes_agent.py`（预算/限流/异常） | `errMsg` → 恢复面板（recoveryAction） | `render.go` `renderRecoveryPanel` |
| `[DONE]` | 终止帧 | 结束本轮 | `stream.go` |

meta（`eventMeta`）：`runtime`、`node`、`phase`、`session_id`、`elapsed_ms`、`retry` —
TUI 全部解析，用于 workflow 状态栏与 timeline（`types.go`、`main.go` `nodePulseMsg`）。

**盘点发现（如实标注）**：`tool_progress` 是后端合同内事件但 TUI 未展示；
不影响正确性（不丢结论），属 T03/T02 可选的展示增强，不阻塞 T00 验收。

## 4. 运行依赖清单（命令 → 后端 → 数据/模型）

| 依赖 | 现状（本机） | 被谁消费 | 备注 |
|---|---|---|---|
| `POST /api/agent/stream`（FastAPI） | **未启动**（8000 无响应，`curl /readyz` = 000） | 全部 prompt/local 问答命令 | TUI 唯一问答路径；请求体 `{question, history, session_id, retry}` 与 `AgentRequest` schema 完全匹配 |
| 后端 Agent 编排（LangGraph runtime） | 随后端未启动 | `/verify` 等 | `backend/app/agent/langgraph_runtime.py` |
| LLM（`GET /v1/models`，默认 `127.0.0.1:8001`） | **未启动**（8001 无响应） | Agent 推理 | doctor 检查项 LLM；`SCISCOPE_HOSTED_BACKEND` 可切 hosted |
| PostgreSQL pgvector（`sciscope-db`，5433） | **Up 23 小时** | papers/chunks/chunk_embeddings/stance 等 | 本机 5432 被其他库占用，需 `SCISCOPE_DB_DSN=postgresql://tim@localhost:5433/sciscope`（见 G00 §4） |
| `paper_embeddings`（推荐用向量表） | **缺失** | `recommend_papers` | 归 G03（2080 Ti），当前工具调用会异常（非结构化降级，留 G02） |
| 图谱资产 `output/graphs/{author,keyword,paper_topic,graph_metrics}.json` | **存在**（4 个 JSON） | `/doctor` Graph assets 检查、`query_knowledge_graph` 结果 | doctor 检查路径 `output/graphs` |
| skill 模板 `.sciscope/skills/*.md` | **存在**（5 个：claim-check / literature-review / paper-recommendation / report-editor / trend-analysis） | `/verify` `/review` `/trend` `/recommend` | `{{input}}` 占位替换；模板缺失时回落 fallback 提示 |
| 会话目录 `~/.sciscope/sessions` | **存在**（69 个 Markdown） | `/sessions` `/resume` `/export` `--last` | 每轮完成自动落盘 |
| golden session | 存在 | 演示/交付 | `docs/examples/golden_verify_claim_session.md` |

## 5. 验证等级与在线状态

### 5.1 静态验证（已执行）

- `rtk go test ./...`（`tui/`）：**91 passed in 1 packages**，退出码 0。
- 覆盖面：SSE 事件渲染（plan/reflect 内联、tool 事件 timeline、final 刷新）、
  7 种结果卡（evidence/verify/trend/通用/恢复面板）、slash 注册与执行、skill 模板加载、
  doctor 报告、demo 脚本、会话持久化与恢复、语义高亮、recovery 分类、CLI 解析。
- 静态调用链（人工）：`slash.go` 16 命令 ↔ `commands_run.go`/`main.go` 执行器一一对应；
  `stream.go` 事件解析 ↔ `events.py` 合同一致（除 `tool_progress` 未展示，见 §3）。

### 5.2 在线状态（本机，2026-08-05）

| 检查 | 结果 |
|---|---|
| Backend `http://127.0.0.1:8000/readyz` | ❌ 未启动（curl 000） |
| LLM `http://127.0.0.1:8001/v1/models` | ❌ 未启动（curl 000） |
| `sciscope-db` 容器 | ✅ Up 23 小时（5433） |
| `output/graphs/` | ✅ 4 个资产存在 |
| `~/.sciscope/sessions/` | ✅ 69 个会话 |

未做在线联调（后端/LLM 未启动），不猜测成功；真实在线演练归 T04。

## 6. 明确排除（诚实边界）

| 排除项 | 依据 | 归属 |
|---|---|---|
| 新 PDF 解析 / 任意 PDF 上传 | TUI 无上传、无解析代码；`/verify` 等只把文本问题交给后端 | D 线（Python 数据层受控摄取） |
| 交互式图谱浏览（图可视化/`/graph` 命令） | TUI 无图谱渲染；`query_knowledge_graph` 仅以文本卡展示查询结果 | G 线（不重建 Web 图谱浏览器；先交付可查询摘要） |
| 在 TUI 重新计算关系 / stance / 推荐 | 所有计算结果来自后端 `tool_result`，TUI 只渲染 | 后端 Agent + G02/A02/E03 合同 |
| 承载 Agent 推理 / 检索 | TUI 不调用 LLM、不做向量检索 | 后端 Agent 编排 |

## 7. 与 A/G/E 输出合同对应

| 合同 | 状态 | TUI 对应点 |
|---|---|---|
| A02 答案/引文/拒答合同 | `PENDING`（A 线） | `final`/`text` 事件 + 研究结论块 + 证据工具脚注；结构化 schema 落地后 T02 绑定渲染 |
| G02 图谱/推荐/趋势查询合同 | `PENDING`（G 线） | `get_trends` 趋势卡（已按"不暴露内部指标"渲染，`trendDirection/Stage/Basis`）；`recommend_papers`/`query_knowledge_graph` 落通用卡 |
| E03 同 claim 争议三读 | `PENDING`（E 线） | 后端 `list_disputes` 工具已存在；TUI 目录未列（§2 差异），争议卡展示归 T02，不可把相反句子硬拼为争议 |
| E07 演示证据 | 依赖 T04 | `/demo`、golden session 现成可复现 |

## 8. 结论与下游衔接

- **PASS**：16 命令无幽灵；SSE 消费与后端合同一致（`tool_progress` 未展示为已知差异）；
  工具目录与后端注册表 9/11 对应，差异如实标注；排除项明确。
- 衔接：T01（命令/黄金任务）依赖本表 + A02；T02（结果卡）需在 A02/G02/E03 落地后，
  把 `list_disputes`、`delegate` 补入目录，并做争议/推荐/图谱卡。
- 风险/回退：本任务只读，未改代码；在线未验证项由 T04 兜底；推荐线受 G03 `BLOCKED` 阻塞时
  T02 以"无 embedding 降级"口径展示。
