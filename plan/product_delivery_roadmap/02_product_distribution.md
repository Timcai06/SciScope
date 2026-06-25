# 最终用户产品分发计划（v1）

## 产品定位（产品级边界）

SciScope 的交付链条采用 **“TUI 为主线、Web 为观察入口”** 的分发策略：

- 主交互和核心价值承载在终端：`sciscope-tui`（Go）消费 `POST /api/agent/stream`，用于高频科研问答、证据追踪、会话恢复与导出。
- Web 前端（Next.js）作为观览与下载入口：用于展示 Dashboard、趋势/图谱结果、报告与下载，不承接终端的主线交互。
- 后端（Python）与数据层负责全部检索、RAG、证据、趋势和图谱推理能力，TUI 与 Web 共用同一套接口。

> 关键边界：发布面向用户时以 `sciscope-tui` 作为主要可交付二进制；  
> 文档、下载与观览体验通过 landing + frontend 承接，不与 TUI 功能主线抢位。

## 用户旅程

### 1) 首次接触

用户通过 landing 或社区渠道看到三类信息：

- 我能做什么：文献问答、趋势洞察、推荐、知识图谱和报告导出。
- 我该如何安装：按系统选择安装矩阵（见下文）。
- 安装成功后先看什么：先跑一次 `/demo`，确认输出可读。

### 2) 安装与首次启动

- 安装 TUI 后执行：
  - `make backend`（服务端）
  - `make llm`（可选，本地 LLM）
  - `sciscope-tui`（启动终端客户端）
- 首次进入应直接看到仪表提示，快速引导可见 `/demo`、`/sessions`、`/help`。
- 若环境未就绪，`/doctor` / `sciscope-tui doctor` 给出可执行修复建议。

### 3) 常态使用

- 核心路径：在终端输入问题 → 观察 `plan/tool_call/tool_result/reflect/final` 流程 → 根据证据决定后续检索。
- 产出路径：会话自动保存 `sciscope-session-YYYYMMDD-HHMMSS.md`，支持 `/export` 导出、`/sessions` 恢复、`/retry` 重试。
- 外部交付：由前端入口查看 Dashboard / 报告 / 图谱视图，并从 landing 下载报告或补充文档。

### 4) 问题反馈

- 用户异常优先在 TUI 内完成初检（`/doctor`、`/help`、`/retry`）。
- 再升级到文档链路（README/运行手册/发行说明）和反馈渠道（待补齐：官方工单地址）。

## 安装方式矩阵

| 平台 | 安装方式 | 适用范围 | 命令/说明 | 当前状态 |
|---|---|---|---|---|
| macOS | Homebrew（首选） | 终端用户 | `brew install Timcai06/sciscope/sciscope-tui` | 已有文档，链路在 `docs/release/tui-homebrew.md` |
| macOS | 本地编译二进制 | 开发者 / 私有环境 | `make tui-build TUI_VERSION=<x.y.z>`，生成 `tui/sciscope-tui` | 已支持 |
| macOS | 源码运行 | 无安装器场景 | `cd tui && GOCACHE=.cache/go-build go run .` | 已支持（依赖 Go） |
| macOS/Linux | 二进制直接下载安装 | 无 brew 的离线环境 | `tui/.goreleaser.yaml` 定义了 `darwin/linux` 打包；发布页下载路径待补齐 | 待补齐 |
| Linux | Homebrew/Linux 包分发 | 稳定交付通道（待落地） | 待补齐：是否接入 Linuxbrew/脚本包 | 待补齐 |
| Windows | 二进制安装 | 未来路径 | 目前发布配置未定义可用 Windows 终端安装链路 | 待补齐 |

> 备注：发布流程当前与 `.github/workflows/release.yml`、`tui/.goreleaser.yaml` 对齐，支持 tag 驱动构建，需在 PR/主线上明确交付时点。

## TUI 首次启动体验设计

### 目标体验（MVP）

- 命令最短路径：  
  1. 启动服务：`make backend`  
  2. 可选本地模型：`make llm`  
  3. 启动 TUI：`make tui` 或 `sciscope-tui`
- 首屏显示 splash/quick action：`/demo`、`/sessions`、`/help`，并展示后端/LLM/会话目录状态入口。
- 用户可在首屏直接进入“离线演示”：`/demo` 或 `sciscope-tui --demo`，完成可验证标准输出体验。
- 默认终端字体不满足图标时，支持 `SCISCOPE_TUI_ICONS=off`。

### 首次体验验收项

- 能看到欢迎状态和命令提示，不出现空白界面。
- 能成功运行离线演示（`/demo`），观察到 plan/tool/reflect/final。
- 实际连接后端时，首条问题可返回可读证据链。
- 会话可导出：`/export` 与 `sciscope-tui export --last`。

### 初学者支持（文案要求）

- onboarding 文案建议固定为：
  - “先运行 `make backend`；如果要离线查看演示可直接 `sciscope-tui --demo`。”
  - “若报错，先跑 `sciscope-tui doctor`，按建议命令自修复。”

## landing page 信息架构（不抢 TUI 主线）

### 现状确认

当前 `frontend/app/page.tsx` 直接渲染的是工作台面板（Dashboard、问答、趋势、推荐、图谱），还未形成独立“产品 landing”说明页。

### 目标 IA（建议）

- 首屏：产品一句话、场景价值（科研问答、趋势、图谱）、一键安装区（含安装矩阵入口）。
- 观览区：最近数据洞察（数据范围、论文数量、趋势快照）与报告预览入口。
- 下载区：TUI 版本状态、安装命令、常见安装问题与兼容矩阵。
- 文档区：README、runbook、TUI 说明、release guide、常见 FAQ。
- 观测区：示例会话截图/输出片段，用于降低首次门槛。

### 交付原则

- landing 只承载“看得见、可下载、可开工”；  
  真正工作流仍由 TUI 与终端命令驱动。
- Web 前端将保持“观览/报告/下载”定位，不替代 TUI 的 `/agent` 交互与会话编排。

### 待确认

- 是否新增独立 landing 路由（如 `/` 与 `/landing` 分离）。  
- 是否把导航中的报告下载与安装指南做可跳转组件化抽离。  
- 是否为 Windows 提供可视化下载说明页（待补齐）。

## 版本发布策略

### 当前可执行链路（已有）

- 标签驱动发布：Push `v*` tag 触发 `.github/workflows/release.yml`。
- 打包工具：`tui/.goreleaser.yaml`。
- 分发优先：`sciscope-tui` Homebrew Cask 到 `Timcai06/homebrew-sciscope`。
- 版本注入：`-X main.version={{ .Version }}`，`make tui-build TUI_VERSION=<ver>` 可本地演练。

### 发布口径

- TUI 为当前唯一明确的终端交付产物；后端、数据库、模型资产不在 Homebrew 发布范围内（需要用户按项目文档部署服务端）。
- `make tui-demo`、`make tui-doctor`、`make tui-export-last` 为发布前一致性验收。

### 路线图

1. 稳定 macOS 主线：保持 cask 为首选入口。
2. 增加 Linux 可执行文档入口：在 release note 中明确下载链接、校验方式与安装示例。
3. 完善 Windows 路线：先发布说明（WSL/手工编译）再决定是否接入独立分发格式。
4. landing 统一指向“安装矩阵 + 版本日志 + FAQ + 文档”并减少重复说明。

## 用户支持与诊断

### 自助诊断标准流程

1. `sciscope-tui --version`：确认客户端版本。
2. `sciscope-tui doctor`：检查后端/LLM/会话目录/图谱资产状态。
3. `make smoke`：服务基础健康检查。
4. `make tui-doctor`：CI/发布前同源检查。
5. `sciscope-tui export --last`：导出异常会话用于反馈。

### 常见问题路径（用户可见）

- 后端不可达：提示“先启动 `make backend`”。
- LLM 不可达：提示“用 mock 模式或先 `make llm`”。
- 图谱缺失：提示“先 `make graph-export`”。
- 会话无法恢复：建议执行 `/sessions` 并重新 `/resume 1`（最近会话）或检查会话目录权限。

### 支持闭环（待补齐）

- 建议补充支持渠道（Issue 模板、FAQ 分类、反馈响应 SLA）。
- 建议沉淀“5 分钟故障排查脚本”到 landing 的帮助页，与文档入口一并发布。
- 建议在每个版本附带“已知问题/兼容性”清单。

## 与交付目标的一致性说明

- 这份分发计划的核心是：把 SciScope 的可发布主线集中到 TUI，同时让 Web 成为可信、可审阅、可下载的入口层。  
- 任何新增 Web 特性都不应吞掉终端主线价值；TUI 仍是用户第一次完成“研究工作流”的起点。  
- 不确定项已按要求用“待补齐”标记，避免误导用户或写入未落地命令。
