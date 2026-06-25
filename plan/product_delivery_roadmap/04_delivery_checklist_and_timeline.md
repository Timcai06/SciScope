# SciScope 完整交付清单与时间线计划（赛题交付 + 最终用户产品化）

本计划基于当前仓库结构与实现现状，仅记录可执行的交付步骤。凡未在仓库中找到明确实现路径的项，标记为“待补齐/待确认”。

## 目标分层

### 赛题交付目标
- 输出可复现、可核验的文档与模型交付成果（含 `数据分析报告`、`科研智能体` 成果链路）。
- 保证指标口径一致：原始采集 / 分析资产 / 入库语料 / 报告资产分层清晰。

### 最终用户产品化目标
- 形成面向真实用户的“工作流可信体验”：前端能稳定消费后端能力、TUI 与 SSE 协议一致、关键链路可一键演示。
- 完成交付收敛：发布、落地页、验收闭环。

## 总时间线（先产品力，后交付收敛）

| 阶段 | 时间窗 | 主要交付 |
|---|---|---|
| 1 产品体验打磨 | W1-W2 | 前端工作流打磨、Dashboard 与数据展示稳定 |
| 2 LangGraph 工作流升级 | W3-W4 | 流式运行时收敛、回归与恢复策略固化 |
| 3 报告与固定产物 | W4 | 数据/项目报告与评测资产固定化 |
| 4 打包发布 | W5 | TUI 打包发布链路闭环、版本化 |
| 5 landing page | W6 | 外部展示页与产品入口收口 |
| 6 最终验收 | W7 | 赛题与产品化双线验收通过 |

> 其中“W”表示按周推进；当前阶段建议从下一个计划日（T0）开始，按顺序执行。

---

## 1）阶段：产品体验打磨

### 阶段目标
以产品可用性为主，先把用户触点打磨到可演示、可复用、可解释的状态，再做交付收敛。

### 关键任务
- 核对前端关键入口是否直接绑定真实服务而非静态 mock：
  - `frontend/src/components/DashboardOverview.tsx`
  - `frontend/src/components/EvidenceChat.tsx`
  - `frontend/src/components/SearchPanel.tsx`
  - `frontend/src/components/TrendsPanel.tsx`
  - `frontend/src/components/RecommendPanel.tsx`
  - `frontend/src/components/GraphPanel.tsx`
  - `frontend/app/page.tsx`
  - `frontend/src/api/client.ts`
- 统一体验语义：错误文案、loading、空态、证据不充分提示，避免“无后端时看起来成功但数据空洞”。
- 检查并补齐导航语义与一级信息入口（当前 `AppShell` 以研究工作台为主，未见独立 Report Studio 路由入口行为）。
- 优先保证 `/api/dashboard/overview`、`/api/search`、`/api/trends`、`/api/recommend`、`/api/graph`、`/api/chat` 在本阶段具备一致降级信息。

### 关键文件/产物
- `frontend/src/api/client.ts`（接口路径与错误语义）
- `frontend/src/app/page.tsx`
- `frontend/src/components/*`
- `frontend/src/types.ts`
- `frontend/app/globals.css`（主题与可读性）

### 负责人角色建议
- 产品/PM：定义演示脚本（“三分钟体验路径”）
- 前端：组件状态、导航结构、可视化一致性
- 后端：接口稳定性与错误码语义对齐

### 验收标准（阶段内）
- `make dev` + 浏览器访问 `http://localhost:3001` 能完整加载真实数据概览卡片。
- 至少 5 条核心查询路径可演示：
  - Overview（总量与年限）
  - Search（检索结果返回）
  - Trends（趋势卡片与不确定性说明）
  - Recommend（推荐与评分因子）
  - Evidence Chat（含证据卡/置信度）
- 不可出现“界面成功但全部空内容且无错误原因”的 silent fail。

### 风险与依赖
- 依赖：`make dev` 联合启动后端端口 `127.0.0.1:8000`、`SCISCOPE_DB_DSN` 配置及 corpus 可用状态。
- 风险：前端现有布局更偏向“研发工作台”，若未统一交互文案会被评委判定为展示不足；需在该阶段补足交互闭环。

### 做 / 不做边界
- 做：稳定体验、可复现演示路径、错误可解释性、真实接口打通。
- 不做：新增“机会生成器/高级预测模块”（当前架构目标更偏先打磨主链路）——标注“待补齐/待确认”。

---

## 2）阶段：LangGraph 工作流升级

### 阶段目标
将智能体从“可跑”升级为“可控可评估”状态：统一为单一 LangGraph 运行时，明确节点级可观测与恢复机制，避免运行时抖动时不可诊断。

### 关键任务
- 梳理当前运行态边界（已确认）：
  - 稳定入口：`backend/app/agent/runtime.py`（仅委托 LangGraph，无运行时开关）。
  - LangGraph 实现：`backend/app/agent/langgraph_runtime.py`。
  - 共享原语：`planning.py` / `reflection.py` / `tool_runner.py` / `llm.py`。
  - 统一事件模型：`backend/app/agent/events.py`。
- 落地“生产级”运行指标：每次 `plan/execute_tools/reflect/final` 的 `meta` 要完整可观测（已有基础字段 `runtime/node/elapsed_ms`）。
- 强化 SSE 契约回归：`backend/app/api/routes_agent.py` 的 `POST /api/agent/stream` 与 `/api/agent`。
- 在本阶段补齐“会话恢复”与 `/retry` 的复测脚本覆盖。

### 关键文件/产物
- `backend/app/agent/runtime.py`
- `backend/app/agent/langgraph_runtime.py`
- `backend/app/api/routes_agent.py`
- `backend/tests/test_agent_runtime.py`

### 负责人角色建议
- 智能体负责人：工作流节点、事件、恢复逻辑
- 后端测试负责人：回归用例、异常路径覆盖
- 运维/平台：部署参数稳定性（模型可用性、langgraph 依赖、checkpoint 存储）

### 验收标准（阶段内）
- Agent 运行态唯一为 LangGraph StateGraph，`langgraph` 为 `make install-backend` 硬依赖。
- SSE 事件顺序稳定、meta 字段在关键节点可解析。
- `make test-backend` 不因工作流切换失败（特别是 `backend/tests/test_agent_runtime.py`）。
- `retry=true` 请求不丢会话上下文（`session_id` 与回放链路保留）。

### 风险与依赖
- 依赖：本地/云侧模型可用（DeepSeek 或 vLLM）、数据库服务（涉及检索工具调用）。
- 风险：工具侧返回质量波动会放大到重试策略误触发；需保持提示词中的“证据优先”约束。

### 做 / 不做边界
- 做：工作流稳定性、观测性、回退策略、可验证 meta。
- 不做：在本阶段重写工具模型（tools）本身的检索算法；如有提升需求改为下一迭代“待补齐/待确认”。

---

## 3）阶段：报告与固定产物

### 阶段目标
把“结果可复现”与“交付口径固定”落到资产层，确保比赛提交和用户展示使用同一份可追溯资产。

### 关键任务
- 确认 `make data-layer-refresh`、`make report-figures`、`make data-report-pdf` 的固定执行顺序。
- 固定报告链路：
  - 数据分析：`output/assets/sciscope_data_report/`
  - 数据报告 PDF：`output/pdf/sciscope_data_report/sciscope_data_report.pdf`
  - 项目报告 PDF：`output/pdf/sciscope_project_report/sciscope_project_report.pdf`
- 固定图件与清单：`figure_manifest.csv`（两类 report 目录中均有现成 manifest）。
- 复核模型资产文件边界：
  - `models/trends/`
  - `models/recommend/`
  - `output/graphs/`
  - `models/embedder_local/multilingual-e5-base`
  - `output/eval/eval_report.json`
- 对照 `交付说明.md` 的“赛题映射口径”补齐“路径入口与口径定义”。

### 关键文件/产物
- `Makefile`（`report`、`data-layer-refresh`、`data-report-pdf`、`project-report-pdf`）
- `output/assets/sciscope_data_report/`
- `output/pdf/sciscope_data_report/`
- `output/pdf/sciscope_project_report/`
- `output/eval/eval_report.json`
- `交付说明.md`

### 负责人角色建议
- 内容与指标负责人：确认报告章节是否覆盖评分项
- 数据/模型负责人：确认模型文件与图件更新对应关系
- 文档负责人：统一编号、引用与口径（原始/清洗/入库）

### 验收标准（阶段内）
- 命令链路可重复：`make data-layer-refresh && make report-figures && make data-report-pdf` 可重跑出完整产物（允许已处理时间差异，但目录和文件名一致）。
- `sciscope_data_report.pdf` 与 `sciscope_project_report.pdf` 与脚本版本一致，无人工拼接。
- 图件清单文件齐全，主图来源可追溯。

### 风险与依赖
- 依赖：`xelatex` 构建器、`evaluation` 与分析资产生成脚本可用。
- 风险：数据口径混淆（如原始数量、processed 数量、入库数量互相引用），必须在报告中单列口径表；否则复核失败。

### 做 / 不做边界
- 做：数据报告、项目报告与评测包的固定构建闭环。
- 不做：新增“新字段指标定义文档”超出本阶段目标（若有新统计指标，先列入待补齐）。

---

## 4）阶段：打包发布

### 阶段目标
建立可重复发布动作，先完成 TUI 客户端发布闭环（现有链路已存在），并明确后端/前端的发布缺口。

### 关键任务
- 固定 TUI 发布流程：
  - `make tui-build TUI_VERSION=...` 本地产物校验
  - `tui/README.md` 与 `docs/release/tui-homebrew.md` 统一版本描述
  - `.github/workflows/release.yml` + `tui/.goreleaser.yaml` 联动发布策略核验
- 明确发布范围边界：
  - 现有发布只覆盖 Go 客户端（`tui/sciscope-tui` 与 homebrew tap）。
  - 后端、数据库、模型资产不在当前 Homebrew 发布边界（在文档中显式声明）。
- 待补齐项：如需面向最终用户一键部署 web/backend，新增容器化或镜像发布流程。

### 关键文件/产物
- `tui/README.md`
- `docs/release/tui-homebrew.md`
- `tui/.goreleaser.yaml`
- `.github/workflows/release.yml`
- `Makefile`（`tui-build`、`tui-doctor`）

### 负责人角色建议
- 发布负责人：版本号、tag 与 Release 校验
- 运维/构建负责人：CI 与 token、平台权限
- 安全负责人：发布制品哈希与回滚策略

### 验收标准（阶段内）
- 本地：`make tui-build TUI_VERSION=<v>` 可执行，`sciscope-tui --version` 与版本一致。
- CI：推 `v*` tag 后能触发 `.github/workflows/release.yml`。
- 发布边界文档与仓库现状一致（不可误导用户以为发布了完整系统）。

### 风险与依赖
- 依赖：`goreleaser`、Go 运行环境、release token 权限。
- 风险：发布误差（tag 与二进制版本不一致）；须将 `tui-build` 与 CI 产物做一致性比对。

### 做 / 不做边界
- 做：TUI 分发闭环与验证清单。
- 不做：本阶段不把后端/数据库/模型资产纳入同一发布制品（标记为架构边界）。

---

## 5）阶段：landing page

### 阶段目标
在现有工作台入口之上补齐对外展示入口，给最终用户提供“什么是 SciScope、如何开始”的第一接触页。

### 关键任务
- 评估现状：当前 `frontend/app/page.tsx` 即为工作台视图入口（`DashboardOverview + EvidenceChat + Search/Trends/Recommend/Graph`），尚未确认独立 landing 模块。
- 待补齐项（待补齐）：
  - `/landing` 或主页切换为“产品价值说明 + 立即开始按钮”与工作台入口；
  - 跳转到当前 Workspace 的首屏引导；
  - 在评估版本标注“当前是产品工作台版，不是最终营销站”。
- 明确 landing 与 dashboard 的边界：landing 可静态展示，工作台保持数据驱动真实检索。

### 关键文件/产物
- `frontend/app/page.tsx`（是否共用或分拆）
- `frontend/src/components/*`（复用现有组件/导航）
- `frontend/src/api/client.ts`（统一后端基地址）
- `docs/` 下新增 landing 说明页（待补齐）

### 负责人角色建议
- UX/产品：内容结构、转化路径文案
- 前端：路由与首屏实现
- 后端/运维：演示环境可达性与健康检测

### 验收标准（阶段内）
- 访问首页能直观看到“产品定位 + 进入方式 + 示例价值”；
- 1 次点击即可到达可用工作台；
- landing 与工作台的依赖、端口、后端要求不混淆。

### 风险与依赖
- 依赖：设计决策（是否保留当前“首页即工作台”原则）。
- 风险：新增页面与现有 “research command center” 风格冲突；建议以最小内容替代重构。

### 做 / 不做边界
- 做：对外可展示结构、最短进入路径。
- 不做：新增复杂内容管理系统（暂不在本阶段）—待后续迭代。

---

## 6）阶段：最终验收

### 阶段目标
按赛题与产品化双轨完成“冻结与交付”检查，避免只过一方不满足另一方需求。

### 赛题验收清单
- `make install`
- `make data-layer-refresh`
- `make full-rebuild`（如做 corpus 已有）或对应最小链路替代
- `make report`（包含报告图件与 PDF）
- `make eval-all`（关键评测留底）
- `make test`
- 运行 `make smoke`
- 产物齐全性：`交付说明.md` 对应文件路径存在且可重建

### 用户产品化验收清单
- `make dev` 能同时启动前后端
- `/api/agent/stream` SSE 与 `meta` 字段可观测
- 前端关键流程从搜索到答复再到图谱/趋势可闭环演示
- `make tui-build` + `make tui-doctor` + TUI 演示可用
- 打包与发布步骤可复现（含版本号、tag、workflow）
- Landing 路由/页面可达（若在本阶段纳入）

### 关键文件/产物
- 全链路命令与产物路径同上
- `docs/runbook.md`（最终交付前统一核对）
- `交付说明.md`（提交口径统一）
- `backend/tests/*`、`frontend` Typecheck/Build

### 风险与依赖
- 依赖：数据库、模型文件、外部模型端口状态、评测环境。
- 风险：环境变量未锁定导致复现性差；建议在验收记录中落地一份“执行环境快照”。

### 做 / 不做边界
- 做：完成双线验收报告、版本锁定记录、待处理项归类为待补齐。
- 不做：未验证项继续声明“待补齐/待确认”并从主版本中剥离。

---

## 交付补充约束（全阶段通用）

- 赛题交付与用户产品化必须共享同一数据源契约，不允许为 demo 临时构造替代数据路径。
- 所有新增动作仅记录在本文件的执行计划和本次计划范围内；不在本阶段无序扩展新产品方向。
- 若路径无法核验，文档中必须使用“待补齐/待确认”，避免形成假承诺。
