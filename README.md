# SciScope

SciScope is a local-first scientific literature intelligence stack.

核心规则（交接口径）：

- Python 是底座：数据治理、RAG、检索、证据接地、Agent 工具编排都在 `backend/` 与 `src/` 体系中实现。
- Go TUI (`tui/`) 是终端客户端，不承载推理，只消费后端的 SSE 事件。
- Next.js 前端 (`frontend/`) 是界面层，复用后端 REST + SSE 接口。

仓库启动面向 Makefile，以下信息优先于旧文档口径。

## 一句话理解项目

- 目标：把论文源数据变成可检索、可问答、可分析的交付资产（图表、报告、证据链）。
- 数据入口：`data/raw`（原始采集）、`data_pipeline`（清洗工具）、`src/harvest`（采集入口）。
- 服务出口：`backend/app` 的 FastAPI（搜索、趋势、推荐、Agent 流式问答）。
- 访问端：
  - 浏览器端：`frontend/`
  - 终端端：`tui/`

项目目录和运行边界见 [`docs/project_structure.md`](docs/project_structure.md)。

## 启动检查（默认 5 分钟）

环境要求：

- Python 3.11+
- Node.js 20+ / npm
- PostgreSQL（RAG/检索链条和 `/api/search` 需要）
- Go（如运行 `make tui`）

### 标准启动（推荐）

```bash
make install
make dev
```

打开：

- 前端：`http://localhost:3000`
- 后端文档：`http://127.0.0.1:8000/docs`

### 常见运行路径

- 后端 + 前端：`make backend`，`make frontend`，或 `make dev`。
- 仅 TUI：`make backend`（先起后端）→ `make tui`。
- 本地模型端到端：先保证可用 OpenAI-compatible 服务，再用 `make dev-vllm`。
- 离线演示：`make tui-demo`。

## 核心命令（按场景）

### 数据层与报告

- `make raw-governance`：原始治理到 `data/raw_canonical`。
- `make analysis-assets-all`：生成 `data/analysis/*`。
- `make processed-corpus`：生成 `data/processed/papers_corpus.json`。
- `make report-figures`：生成图表资源到 `output/assets/sciscope_data_report/`。
- `make data-report-pdf`：生成 `sciscope_data_report.pdf`。
- `make project-report-pdf`：生成项目报告 PDF。
- `make full-rebuild`：从分析资产开始重建入库、向量、模型、图谱与数据报告；原始治理需先跑 `make raw-governance`。
- `make data-layer-refresh`：分析资产 + 语料 + 报表重建的轻量入口。

### 模型层与工具链

- `make rag-chunks`：构建 RAG 块。
- `make postgres-load`：写入 PostgreSQL。
- `make postgres-refresh`：schema + load 的完整刷新。
- `make embeddings` / `make trend-model` / `make recommend-model` / `make graph-export`：模型/图谱资产构建。
- `make agent-build`：`embeddings + trend + recommend + graph` 聚合构建。

### 服务与验证

- `make test`：后端测试 + 前端 typecheck/build。
- `make test-backend`：仅后端测试。
- `make smoke`：基础 API 健康检查。
- `make vllm-smoke`：检查本地 OpenAI-compatible 模型端点。
- `make tui-build TUI_VERSION=0.1.0`：产出 Go 客户端二进制。

## Terminal Agent Client（Go TUI）

终端客户端是“协议消费者”：它不承载模型与检索决策逻辑，只消费
`POST /api/agent/stream` 的 SSE 事件并渲染为可读面板。

启动方式（推荐）：

```bash
make backend  # 先启动后端 127.0.0.1:8000
make llm      # 可选：本地 LLM 兼容网关（用于真实联网问答）
make tui      # 运行终端客户端
make tui-demo # 离线演示流程（无后端）
```

版本与发布链路请见：

- `tui/README.md`
- `docs/release/tui-homebrew.md`

## 交接时一页速查

默认环境变量（运行时有默认值）：

- `SCISCOPE_DATA_PATH=data/sample/papers.sample.json`
- `SCISCOPE_DB_DSN=postgresql://tim@localhost:5432/sciscope`
- `SCISCOPE_USE_MOCK_LLM=true`
- `SCISCOPE_LLM_PROVIDER=deepseek`

关键 API：

- `POST /api/agent/stream`（SSE）：SSE 事件 `plan/text/tool_call/tool_result/reflect/final/error`
- `GET /api/ingest/status`
- `GET /api/dashboard/overview`
- `POST /api/chat`

## 常见故障（先查这里）

- 端口不可达：确认 `make backend` 已启动，访问 `127.0.0.1:8000`。
- TUI 无法显示流式：确认后端先跑，再执行 `make tui`；必要时设置 `SCISCOPE_TUI_ICONS=off`。
- 检索/趋势为空：确认 PostgreSQL 已准备好，执行 `make postgres-refresh` 或至少 `make postgres-load + make rag-chunks`。
- LLM 报错：切回 `SCISCOPE_USE_MOCK_LLM=true` 做快速验证；或先 `make llm` 提供本地模型。
- 图表/PDF 缺失：检查 `data/analysis` 和 `output/assets/sciscope_data_report`，再跑 `make report-figures && make data-report-pdf`。

## 现有边界

- 该分支的主运行路径是：Python agent/data layer 为核心，Go TUI 为终端消费端。
- DeepSeek 路径当前以配置占位为主；确定性本地验证以 mock 模式为主，LLM 本地通路以 `make dev-vllm` / `make llm` 为主。
