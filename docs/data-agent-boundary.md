# 数据链路与 Agent 边界说明

## 一、链路总览（交接边界）

- `data/raw/*.jsonl` → `build_raw_canonical` → `data/raw_canonical/<source>/<year>.jsonl`
  - 目标：输入治理、去重、分源分年归一化、可审计清单化。
  - 产物中保留 `_sciscope_*` 元数据作为跨阶段追踪标记。
- `data/raw_canonical`（含 `future_year_suspect.jsonl` 外移语义）→ `build_analysis_assets` → `data/analysis`
  - 目标：产出分析态语料与特征表（papers_clean、taxonomy、关键词、作者、趋势/社区等）。
- `data/analysis/papers_clean.json` → `build_processed_corpus` → `data/processed/papers_corpus.json`
  - 目标：去重与前沿窗口标记（`is_recent_window`）后的处理语料。
- `data/processed/papers_corpus.json` → `build_chunk_assets`（`build_paper_chunks`）→ `data/processed/paper_chunks.jsonl`
  - 目标：检索可用文本块（title+abstract/full_text/keywords）并保留 chunk 元信息。
- `data/processed/{papers_corpus, paper_chunks}` + schema SQL → `import_postgres`
  - 目标：加载到 PostgreSQL（papers/paper_authors/coauthor_edges/paper_chunks）。
- `chunk embeddings` 与 `papers` 表 → `build_embeddings`
  - 目标：生成 `chunk_embeddings`（pgvector）与 `paper_embeddings`（推荐用）。
- `keyword/author/topic/...` 资产 → `recommend_model / trend_model / graph_export`
  - 目标：支撑趋势、推荐和图谱服务侧调用。
- `data/analysis + output/graphs + report assets` → `build_report_figures / data-report-pdf`
  - 目标：产出可复核报告图件与 manifest，支持人工核对。

## 二、raw canonical 与 quarantine 边界

- `build_raw_canonical` 将未来年份记录标记为 `future_year_suspect`，不直接硬删。
- `_sciscope_year_status` 与 `_sciscope_original_year` 记录“可疑年份”轨迹；
  这样可以在数据层审计和后续质量评估中保留复核证据。
- `archive_dir` 参数用于把本次输入源文件移动到“准隔离/待审”区；
  `delete_archive=True` 才清理隔离区。该行为用于保留重跑溯源能力。
- `raw_inventory.csv` 与 `summary.json` 是链路证据，不作为模型真值的直接输入。

交接提醒：`make full-rebuild` 不包含 raw governance；如果原始采集文件有更新，先执行
`make raw-governance`，再进入 `make full-rebuild` 或分步重建链路。

## 三、processed-corpus 与 chunks 边界

- `build_processed_corpus` 使用 `data/analysis/papers_clean.json`；保留 `is_recent_window`（默认 `2022~2026`）。
- `build_paper_chunks` 输出 `chunk_uid/paper_uid/chunk_type/source_field/token_estimate`；
  该层是检索与推荐系统对齐的统一语义粒度边界。
- 任何 full-text 噪声（PDF 污损结构文本）会在 chunk 前过滤，避免污染 embedding。

## 四、Postgres / pgvector 边界

- `import_postgres` 的写入目标是“服务层真值表”；
  `papers/paper_chunks/chunk_embeddings/paper_embeddings` 的存在决定检索可用性。
- 检索工具 `search_literature` / `recommend_papers` / `get_trends` 全部走这个层：
  不是本地模型自由发挥，而是以 `paper_uid`/`paper_id` 显式主键为依据返回证据。 

## 五、Agent 工具边界（`backend/app/agent/tools.py`）

- 代理工具集合固定为：
  `search_literature`, `get_trends`, `recommend_papers`, `get_paper`, `summarize_field`, `compare_papers`, `export_bibliography`, `query_knowledge_graph`, `verify_claim`。
- 工具是 **读模型边界**（无数据写入动作）；
  若输入为空、参数异常或服务不可用，返回“可展示错误字符串”，交给循环再决策重试。
- `loop.py` 通过 `TOOL_SCHEMAS` + `run_tools` 并发、去重签名，限制同参同参重复调用。

## 六、`verify_claim` 边界

- `verify_claim(claim)` 的流程是：
  1) 检索候选证据 6 条；2) `title+snippet` 组成 evidence text；3) e5 语义编码，按余弦相似度给出：
  - `>= 0.84`：强支持
  - `0.78~0.84`：部分支持
  - `< 0.78`：证据不足
- 输出是“支持等级+前若干证据”，模型/人工需据此约束结论力度，不可当成逻辑断言引擎。

## 七、报告资产边界（`build_report_figures`）

- `figure_manifest.csv` 是报告消费入口清单（而不是原始决策依据）。
- 每张图只绑定一个 source table（`source_quality_report.csv`、`keyword_year_matrix.csv` 等），
  便于逐项核对：哪个图使用了哪份分析文件。

## 八、相关文档入口

- `docs/project_structure.md`：目录结构、责任边界与生成产物约定。
- `docs/runbook.md`：运行命令、环境变量、验收命令与故障处理。
- `交付说明.md`：面向评审/交付的成果索引与指标口径。
