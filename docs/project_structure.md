# SciScope 项目结构（交接版）

SciScope 以 **Python 数据智能底座 + Go TUI 终端客户端** 为主要交接边界，目录层级按职责切分。

- Python 承载数据治理、RAG、检索、证据接地和 Agent 逻辑。
- `backend` 与 `src` 是核心运行逻辑层，`tui` 只消费 SSE。
- Web 前端源码已移除；当前客户端边界是 Go TUI 与 FastAPI API。

## 六层职责（从底到上）

1. 数据层
   - `data/`：可重建资产层，不是 PostgreSQL 的重复备份。
   - `data/raw/`：新增采集 landing zone，治理后可清空到 `.gitkeep`。
   - `data/raw_canonical/`：source/year 分区的原始底账，支持审计与重建。
   - `data/analysis/`：报告、趋势、关键词/作者网络的分析资产。
   - `data/processed/`：`papers_corpus.json` 与 `paper_chunks.jsonl`，是 PostgreSQL/RAG 的导入边界。
   - `data_pipeline/`：legacy sample pipeline，服务旧 sample tests 和兼容层；核心生产链路以 `src/` 为准。

2. 模型与索引输入层
   - `src/harvest/`：源采集与文本补全
   - `src/analysis/`：报告与分析资产计算
   - `src/models/`：模型/索引相关脚本（embedding/recommend/trend 等）

3. 服务层
   - `backend/app/services/`：检索、GraphRAG、证据问答、趋势与推荐服务
   - `src/infra/` + `infra/postgres/`：PostgreSQL schema 与装载 CLI/SQL

4. Agent 层
   - `backend/app/agent/`：stream_agent 工具循环与可执行工具集合

5. 接口层
   - `backend/app/api/`：REST 和 SSE 接口（含 `routes_agent.py` 的 `/api/agent/stream`）
   - `backend/app/main.py`：FastAPI 入口

6. 客户端层
   - `tui/`：Go/TUI 协议客户端（SSE 消费）

## 目录总览

```text
数据要素/
├── backend/                  FastAPI（服务/接口/模型）
│   ├── app/
│   │   ├── api/
│   │   ├── agent/
│   │   ├── core/
│   │   ├── models/
│   │   └── services/
│   └── tests/
├── data/                     原始数据到标准化资产
│   ├── raw/
│   ├── raw_canonical/
│   ├── raw_archive/ (运行时生成)
│   ├── processed/
│   ├── analysis/
│   └── sample/
├── data_pipeline/            legacy sample pipeline / 兼容层
├── docs/                     交接、竞赛资料、runbook、发布说明
├── evaluation/               检索/推荐/趋势评估
├── infra/                    PostgreSQL SQL 与部署相关配置
├── models/                   模型文件（常见 Git 忽略）
├── output/                   报告图表、PDF、评估结果
│   ├── assets/
│   ├── eval/
│   ├── graphs/
│   ├── logs/
│   └── pdf/
├── plan/                     任务与路线文档
├── scripts/                  辅助脚本
├── src/                      核心数据工程与模型脚本
│   ├── harvest/
│   ├── analysis/
│   ├── infra/
│   └── models/
├── tui/                      Go 终端客户端
├── configs/                  配置文件与示例
├── .github/                  流水线与发布工作流
├── Makefile                  全部可执行交接口
└── README.md
```

## 运行关系（交接最重要）

- `data` / `src/harvest`：采集、治理与分析资产源。数据库可由它们重建，不能替代它们的审计角色。
- `data/analysis` + `src/models`：输出数据视图与模型训练/重排输入。
- `backend/app/services`：构建检索/证据/趋势/推荐功能与 `/api` 套件。
- `backend/app/agent`：单一 LangGraph StateGraph 编排 prepare / plan / llm_step / execute_tools / reflect / force_synthesis；`session_id` 映射 LangGraph `thread_id`，支持同会话 `/retry` 错误恢复；统一经 SSE（`/api/agent/stream`）对外输出。`runtime.py` 为稳定入口，`langgraph_runtime.py` 为编排实现，`planning/reflection/tool_runner/llm/events` 为共享原语。工具层走契约化 `Tool` 注册表(`tools.py`)；`mcp_server.py` 把工具经 MCP 暴露给外部客户端,`mcp_client.py` 消费外部 MCP 服务,`specialists.py` 提供 `delegate` 派生的专员子智能体(reviewer/trend/critic)。详见 `docs/mcp.md`。
- `tui`：当前主交互端。
- Web 前端不在当前范围；相关源目录已删除。

## 数据链路（按 Makefile 命令）

- `make harvest-*` → `make raw-governance` → `make analysis-assets-all`
- `make processed-corpus` → `make rag-chunks`
- `make postgres-load` / `make postgres-refresh` → `make embeddings`
- `make recommend-model` / `make trend-model` / `make graph-export`
- `make report-figures` → `make data-report-pdf` / `make project-report-pdf`

`make full-rebuild` 是 raw governance 之后的默认重建入口；`make agent-build` 为模型侧快速重建入口。
项目报告更新入口是 `make project-report-pdf`；该目标会先跑 `project-report-figures`，从 `data/analysis`、`data/processed` 和 `output/eval` 读取最新资产。

## 接口与发布边界

- `POST /api/agent/stream`：Go TUI 消费的唯一 Agent 流式协议；请求支持 `question/history/session_id/retry`，SSE `meta` 返回 `runtime/node/elapsed_ms/session_id/retry`。
- `/api/chat`：基于证据的固定式问答（非规划式 Agent）。
- `make tui-build`：产出 `tui/sciscope-tui`（仅客户端二进制）。
- Homebrew 只覆盖 Go 客户端，不包含 Python 后端、数据库和大模型制品。
- 数据治理与 Agent 工具边界见 `docs/data-agent-boundary.md`。
- `plan/archive/` 仅作历史决策记录；当前可执行口径以 `README.md`、本文件、`docs/runbook.md`、`docs/data-agent-boundary.md` 与 `Makefile` 为准。

## 生成产物与 Git 约定

以下目录或文件通常由 Make/脚本生成，原则上通过仓库入口命令复现，不建议手工编辑：

- `data/`（除 `data/sample/`）
- `models/`
- `output/graphs/`
- `tui/sciscope-tui`, `tui/dist/`

其中 `data/raw_canonical/`、`data/analysis/`、`data/processed/papers_corpus.json`、`data/processed/paper_chunks.jsonl` 是可复现交付资产，不能因为 PostgreSQL 已加载而删除；如需节省空间，应先归档而不是直接删除。

## 常见入口文件

- `docs/project_structure.md`：结构与责任边界
- `docs/runbook.md`：启动、验证、故障处理
- `README.md`：项目入口与常用命令
