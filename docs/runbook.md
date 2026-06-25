# SciScope Runbook

This runbook is the practical handoff guide for SciScope foundation operations.
It is aligned to `Makefile` targets and current code behavior.

## Scope and Priority

- Use Makefile targets as the source of truth for runnable workflows.
- `docs/project_structure.md` defines directory ownership and boundaries.
- When behavior conflicts with text in older notes, runtime code + Makefile wins.

## Requirements

- Python 3.11+
- Node.js 20+ and npm
- PostgreSQL (for RAG/search/trends/recommend workflows)
- Go (for local TUI build/run)

## Service Ports and Defaults

```text
Backend: 127.0.0.1:8000
Frontend: 3001
vLLM server: 127.0.0.1:8001
```

## 常用环境变量（默认值可覆盖）

```bash
export SCISCOPE_APP_NAME=SciScope
export SCISCOPE_ENV=local
export SCISCOPE_DATA_PATH=data/sample/papers.sample.json
export SCISCOPE_CORS_ORIGINS=http://localhost:3001
export SCISCOPE_DB_DSN=postgresql://tim@localhost:5432/sciscope
export SCISCOPE_USE_MOCK_LLM=true
export SCISCOPE_LLM_PROVIDER=deepseek
```

## 5 分钟起步

```bash
make install
make dev
```

打开：

- Frontend: `http://localhost:3001`
- Backend Docs: `http://127.0.0.1:8000/docs`

## 运行入口

### 全栈联动（推荐）

```bash
make dev
```

- 同时启动后端与前端。

### 后端独立

```bash
make backend
```

### 前端独立

```bash
make frontend
```

### Go TUI

```bash
make backend   # first
make tui       # consume /api/agent/stream
```

离线演示：

```bash
make tui-demo
```

## 数据与报告链路（常用）

```bash
make raw-governance
make analysis-assets-all
make processed-corpus
make data-layer-audit
make rag-chunks
make postgres-refresh
make report-figures
make data-report-pdf
```

关键一键入口：

```bash
make full-rebuild        # 分析资产后的一键重建：RAG+模型资产+报表
make data-layer-refresh  # 分析资产与报告刷新入口
make agent-build         # embeddings + recommend + trend + graph
```

## 本地模型路径

### 默认（可复现）——Mock

```bash
export SCISCOPE_USE_MOCK_LLM=true
make dev
```

### 本地 OpenAI-compatible 提供者

```bash
make llm       # 启动默认本地模型服务（127.0.0.1:8001）
export SCISCOPE_USE_MOCK_LLM=false
export SCISCOPE_LLM_PROVIDER=vllm
make dev-vllm
```

也可外部提供兼容端点，设置 `LOCAL_LLM_BASE_URL` 与 `LOCAL_LLM_MODEL`。

## 验收与回归命令

```bash
make test
make test-backend
make smoke
make vllm-smoke
make tui-build TUI_VERSION=0.1.0
```

手工接口校验（后端已运行）：

```bash
curl http://127.0.0.1:8000/api/ingest/status
curl http://127.0.0.1:8000/api/dashboard/overview
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"What does RAG improve?"}'
```

## TUI 合约（与后端同步）

```text
POST /api/agent/stream
Content-Type: application/json
Body: {"question":"...", "history":[{"role":"user","content":"..."}]}
SSE events: plan, text, tool_call, tool_result, reflect, final, error
```

## 常见故障与处理

- `connection refused`
  - 确认 `make backend` 已启动，确认 `127.0.0.1:8000` 未被占用。

- `Unable to detect model` / `LLM not found`
  - 临时切回 `SCISCOPE_USE_MOCK_LLM=true`。
  - 或先启动 `make llm` 再回到 `SCISCOPE_LLM_PROVIDER=vllm`。

- 数据库相关错误
  - 检查 `SCISCOPE_DB_DSN`。
  - 运行 `make postgres-schema && make postgres-refresh`。

- `/api/search` 无返回或报未入库
  - 走完整链路：`make full-rebuild` 或至少 `make rag-chunks && make postgres-load`。

- 报表/图片/PDF 缺失
  - 检查 `data/analysis/` 和 `output/assets/sciscope_data_report/`。
  - 执行 `make report-figures && make data-report-pdf`。

- Go TUI 图标错乱
  - 终端不支持 Nerd Font 时，先设置 `SCISCOPE_TUI_ICONS=off`。

## 交接验收最小链

```bash
make install
make full-rebuild
make dev
```

然后：

- 打开 `http://localhost:3001`
- 运行 `make smoke`
- 跑一次 `curl` 提问并确认返回有 `answer` / `evidence`
- 运行 `make tui` 验证 SSE 可达（按需）
