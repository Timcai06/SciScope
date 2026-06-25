# SciScope 赛题交付与复现计划（评委视角）

本计划用于《面向科技文献智能分析的科研智能体构建》评委验收。目标是：**即使评委电脑未安装任何依赖，也能通过源码与固定产物理解并复核关键成果；若愿意配置环境，也可通过可执行路径重现核心指标与端到端行为。**

## 一、目标与验收边界

1. 让评委可在“纯读盘”模式下完成初审：确认需求对应关系、产物完备性、指标口径与证据链。
2. 给出可执行重建路径：从现有数据产物到评估结果，覆盖最少命令与完整链路。
3. 明确稳定真值（固定产物）与可重算产物边界，避免口径混用导致的评审歧义。
4. 对外部条件（数据库、模型服务、LaTeX）不足的情况下仍保持可核验。

## 二、评委无环境验收路径（零依赖可读）

### 2.1 只读核验清单（第一层）

- `交付说明.md`
  - 交付对照、主指标与评测入口说明、关键实现映射（用于赛题口径对齐）
- `docs/competition/赛题.docx`、`docs/competition/数据集.docx`
- `README.md`
- `docs/runbook.md`
- `docs/project_structure.md`
- `output/pdf/sciscope_data_report/sciscope_data_report.pdf`
- `output/pdf/sciscope_project_report/sciscope_project_report.pdf`
- `output/pdf/sciscope_data_report/sections/`、`output/pdf/sciscope_project_report/sections/`

### 2.2 固定产物核验点（第二层）

1. **数据真值链（固定）**
   - `data/raw_canonical/summary.json`
   - `data/analysis/summary.json`
   - `data/analysis/papers_clean.json`
   - `data/processed/papers_corpus.json`
   - `data/processed/papers_corpus.summary.json`
   - `data/processed/paper_chunks.jsonl`
   - `data/processed/paper_chunks.summary.json`
   - `data/analysis/.incremental/*.jsonl`
2. **报告图表与清单（固定）**
   - `output/assets/sciscope_data_report/figure_manifest.csv`
   - `output/assets/sciscope_data_report/*.png`
   - `output/assets/sciscope_project_report/figure_manifest.csv`
   - `output/assets/sciscope_project_report/*.png`
3. **评测与度量（固定）**
   - `output/eval/eval_report.json`
   - `output/eval/eval_report.md`
4. **模型与图谱资产（固定）**
   - `models/trends/{hot_keywords.csv,topic_trends.csv,trend_scores.json}`
   - `models/recommend/recommend_model.json`
   - `output/graphs/{author_graph.json,keyword_graph.json,paper_topic_graph.json,graph_metrics.json}`
5. **服务与客户端边界（固定）**
   - `backend/app/main.py`（路由注册）
   - `backend/app/api/routes_*.py`（REST/SSE 接口定义）
   - `tui/main.go`（终端客户端）
   - `tui/sciscope-tui`、`tui/dist/sciscope-tui_darwin_arm64_v8.0/sciscope-tui`

### 2.3 约束与口径说明（无环境下必须理解）

- 数据层按「**原始采集 → 归一化/分析资产 → 处理语料 → 运行时索引/服务**」分层理解。
- `data/raw_canonical/*/future_year_suspect.jsonl` 为审计留存，不默认进入主口径趋势统计。
- `output/assets/sciscope_data_report/data_layer_readiness.json` 明确了文本覆盖率、年度平衡与缺口行动。
- `output/assets/*/figure_manifest.csv` 说明图表映射到源表和报告章节，适合核对“图都来自何处”。
- TUI 黄金会话样例已提供：`docs/examples/golden_verify_claim_session.md`，用于无环境查看 agent 工作流、证据时间线与最终回答结构。

## 三、有环境复现路径

### 3.1 预备约定

- 默认参数见 `Makefile` 与 `docs/runbook.md`。
- 后端运行环境变量默认：
  - `SCISCOPE_APP_NAME=SciScope`
  - `SCISCOPE_ENV=local`
  - `SCISCOPE_DATA_PATH=data/sample/papers.sample.json`
  - `SCISCOPE_USE_MOCK_LLM=true`
  - `SCISCOPE_LLM_PROVIDER=deepseek`
- 数据库相关默认值见 `Makefile` 的 `POSTGRES_DSN=postgresql://tim@localhost:5432/sciscope`（可替换为评委本机账户）。

### 3.2 最小运行验证路径（不重采集）

适用于仓库已含 `data/raw_canonical`、`data/analysis`、`data/processed` 时。

```bash
make install                 # 安装依赖（Python + frontend）
export SCISCOPE_DB_DSN=postgresql://<user>@localhost:5432/sciscope
make data-layer-refresh      # 生成分析资产 + data report PDF
make postgres-schema         # 无该步骤会影响检索/推荐/趋势测试链
make postgres-load           # 将处理语料导入 PostgreSQL
make embeddings             # 生成/刷新 RAG 片段嵌入
make recommend-model        # 论文推荐模型产物
make trend-model            # 趋势模型产物
make graph-export           # 图谱导出
SCISCOPE_DB_DSN=$SCISCOPE_DB_DSN make eval-all # 产出 evaluation/eval_report.*（需数据库与 embeddings）
make backend               # 启动后端
make smoke                 # 基础 API 可用性自检
```

> 注意：`make smoke` 仅用于“服务可达/基础响应”；若需全链路问答与可复现路径完整性，见 3.3。

### 3.3 全链路复现路径（含服务启动）

```bash
make install
createdb sciscope                             # 需要本机 PostgreSQL
make postgres-schema POSTGRES_DSN=postgresql://<user>@localhost:5432/sciscope
psql postgresql://<user>@localhost:5432/sciscope -f infra/postgres/pgvector.sql
make full-rebuild SCISCOPE_DB_DSN=postgresql://<user>@localhost:5432/sciscope
SCISCOPE_DB_DSN=postgresql://<user>@localhost:5432/sciscope make dev
```

端口与访问口径：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://localhost:3001`
- 后端 API 文档：`http://127.0.0.1:8000/docs`

可复核命令：

```bash
curl -fsS http://127.0.0.1:8000/api/ingest/status
curl -fsS http://127.0.0.1:8000/api/dashboard/overview
curl -fsS -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"RAG 在科学文献分析中的作用是什么？"}'
curl -fsS "http://127.0.0.1:8000/api/search?q=graph+neural+network"
curl -fsS "http://127.0.0.1:8000/api/recommend?paper_id=sample-paper-id"
curl -fsS "http://127.0.0.1:8000/api/trends?hot_limit=10&emerging_limit=10"
curl -fsS "http://127.0.0.1:8000/api/graph?type=keyword&limit=20"
```

> 注意：`sample-paper-id` 需替换为 `papers.sample.json` 或已入库语料中的真实 `paper_id`；`/api/search`/`/api/recommend`/`/api/trends` 的可用性受对应模型资产与数据库状态影响。

### 3.4 TUI 审核路径

- 无后端离线：`make tui-demo`（不依赖数据库与 LLM）
- 已有后端联调：`make tui`
- 会话回看与导出：
  - `make tui-export-last`（若存在历史会话）
  - `sciscope-tui doctor`

## 四、固定产物清单（评委验收锚点）

| 层级 | 路径 | 作用 |
|---|---|---|
| 报告 | `output/pdf/sciscope_data_report/sciscope_data_report.pdf` | 数据交付成品 |
| 报告 | `output/pdf/sciscope_project_report/sciscope_project_report.pdf` | 方案与系统成品说明 |
| 报告源 | `output/pdf/sciscope_data_report/sections/`、`output/pdf/sciscope_project_report/sections/` | 章节级审计源文件 |
| 资产表 | `output/assets/sciscope_data_report/` | 数据图表与 `figure_manifest.csv` |
| 资产表 | `output/assets/sciscope_project_report/` | 评估指标图与系统图 |
| 数据层 | `data/raw_canonical/` | 原始采集归档分区（含 `summary.json`） |
| 数据层 | `data/analysis/` | 统计与图表源表（含 `summary.json`） |
| 处理层 | `data/processed/` | 处理中间语料与 chunk 语料 |
| 评测 | `output/eval/eval_report.json`、`output/eval/eval_report.md` | 检索/趋势/推荐复核证据 |
| 运行模型 | `models/trends/`、`models/recommend/recommend_model.json` | 趋势与推荐模型 |
| 图谱 | `output/graphs/` | 图服务可复用资产 |
| 客户端 | `tui/sciscope-tui`、`tui/dist/.../sciscope-tui` | 终端发布资产 |

## 五、最小复现命令（推荐提供给评委）

### 5.1 评审最小路径（仅核验报告与关键指标）

```bash
make install-backend
make data-layer-refresh
make report-figures
make data-report-pdf
make project-report-pdf
SCISCOPE_DB_DSN=postgresql://<user>@localhost:5432/sciscope make eval-all  # 可选：已建库/已入库时执行
```

### 5.2 关键指标最小路径（含服务与 API）

```bash
createdb sciscope
export SCISCOPE_DB_DSN=postgresql://<user>@localhost:5432/sciscope
make full-rebuild
make backend
# 另开终端执行：
make smoke
curl -fsS http://127.0.0.1:8000/api/dashboard/overview
```

### 5.3 无数据库的最小演示（用于“可启动但不依赖检索链”）

```bash
SCISCOPE_USE_MOCK_LLM=true make backend
# 另开终端执行：
curl -fsS -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"如何理解论文证据接地？"}'
```

## 六、风险、限制与待补齐项

- 已有模型二进制较大且本地路径依赖显著：评审环境若缺少 GPU/模型文件，`make llm`、`make dev-vllm` 等需外部准备。
- `make data-report-pdf`、`make project-report-pdf` 的编译命令包含本机插件脚本路径（`/Users/tim/.codex/plugins/.../compile_latex.py`），路径若不存在请替换为本地可用的 `compile_latex.py` 或标准 `latexmk` 流程，**该处为环境兼容风险**。
- 已提供黄金会话样例 `docs/examples/golden_verify_claim_session.md`；真实 `sciscope-session-*.md` 自动导出快照可在最终提交前按当前版本重新生成并补充。
- 未发现统一的依赖清单文件（如 `requirements.txt` 或 `pyproject.toml`）：**待补齐（待确认）**。
- 命令执行前需明确 `SCISCOPE_DB_DSN`，否则 `/api/search`/`/api/recommend`/`/api/trends` 的部分接口会返回 503 或 400。
- 外部采集与 fulltext enrich 受网络与源站配额影响：本计划默认不要求复原全部历史抓取，按“固定产物复验 + 可控重建”进行验收。

## 七、交付成果确认结论（给评委）

仓库当前已具备“无环境可核验”和“有环境可复现”两层闭环：
1) 无环境层：通过固定产物、章节源码与指标包可核对产出完整性；  
2) 有环境层：通过 `Makefile` 与 API 链路可复现数据分析与服务能力。  
未覆盖项已在风险项中明确标注，便于评委在复核时直接判定是否影响本次赛题验收边界。  
