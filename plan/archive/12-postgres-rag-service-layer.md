# PostgreSQL 与 RAG 服务层实施计划

## 目标

在数据资产层稳定后，将 `data/processed/papers_corpus_50k.json` 转换为可查询、可检索、可扩展的服务层数据底座，支撑文献问答、趋势分析、论文推荐、知识图谱查询与后续 GraphRAG。

## 当前新增能力

- `infra/postgres/schema.sql`：PostgreSQL 基础表结构，包含论文、作者、关键词、论文片段、合作边与全文检索索引。
- `infra/postgres/pgvector.sql`：可选 pgvector 扩展，后续接入 embedding 后启用。
- `src/infra/chunks.py`：从 processed corpus 生成 RAG chunk 资产。
- `src/infra/postgres_loader.py`：将 papers、authors、keywords、chunks、coauthor_edges 分批 upsert 到 PostgreSQL。
- `make rag-chunks`：生成 `data/processed/paper_chunks.jsonl`。
- `make postgres-schema`：应用 PostgreSQL schema。
- `make postgres-load`：导入 processed corpus 与 chunks。
- `make postgres-refresh`：全链路刷新分析资产、报告、schema 与服务层数据。

## 数据表职责

- `papers`：论文主表，承载标题、摘要、年份、领域、来源、全文片段与全文检索向量。
- `authors` / `paper_authors`：作者实体与署名顺序。
- `keywords` / `paper_keywords`：关键词实体与论文关联。
- `paper_chunks`：RAG 检索单元，按标题摘要、正文、关键词生成。
- `coauthor_edges`：作者合作网络服务层数据，供图谱查询和推荐使用。
- `chunk_embeddings`：可选 pgvector 表，后续接 embedding 模型后启用。

## 后续步骤

1. 全量补数完成后运行 `make data-layer-refresh`。
2. 运行 `make rag-chunks` 重建最新 chunk 资产。
3. 本机创建 PostgreSQL 数据库 `sciscope`。
4. 运行 `make postgres-schema POSTGRES_DSN=postgresql://tim@localhost:5432/sciscope`。
5. 运行 `make postgres-load POSTGRES_DSN=postgresql://tim@localhost:5432/sciscope`。
6. 后端增加数据库读取模式：优先 PostgreSQL，失败时回退 JSON corpus。
7. 增加 API：`/api/search`、`/api/recommendations`、`/api/graph/authors`、`/api/trends`。
8. 接入 embedding 生成与 pgvector 检索，形成 hybrid retrieval：FTS + vector + graph context。
