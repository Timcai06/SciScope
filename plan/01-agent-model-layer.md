# Research-Agent Model Layer

How the SciScope research agent is built. The agent is **Python code + model
files**, not just an LLM. The LLM is the generation layer; corpus-specific
intelligence comes from reproducible local models, indices, and the PostgreSQL
serving layer.

## Serving layer (PostgreSQL + pgvector)

`infra/postgres/schema.sql` + `infra/postgres/pgvector.sql`, loaded by
`src/infra/postgres_loader.py` (`make postgres-load`).

- `papers` — title/abstract/year/field/full_text + a generated `search_document`
  TSVECTOR (FTS) with a GIN index.
- `authors` / `paper_authors`, `keywords` / `paper_keywords`.
- `paper_chunks` — RAG retrieval units (title_abstract / full_text / keywords),
  each with its own `search_document` FTS vector.
- `coauthor_edges` — author collaboration edges (capped at
  `max_authors_for_edges=50` to skip pathological mega-author papers).
- `chunk_embeddings(vector(768))` — chunk embeddings (ivfflat cosine).
- `paper_embeddings(vector(768))` — paper-level mean embeddings (built by the
  recommendation step).

Current load: ~160k papers, ~341k chunks, ~3.5M coauthor edges.

## Embeddings

- `src/models/embeddings.py` — local sentence-transformers embedder
  (`intfloat/multilingual-e5-base`, 768-dim to match the schema; e5 `query:` /
  `passage:` prefixes). Cached under `models/embedder/`. Configurable via
  `SCISCOPE_EMBEDDING_MODEL`.
- `src/models/build_embeddings.py` (`make embeddings`) — streams
  `paper_chunks.jsonl`, encodes in batches, upserts `chunk_embeddings`, with
  resume (skips chunk_uids already embedded for the model).

## Retrieval + QA (`/api/search`, `/api/chat`)

`backend/app/services/retrieval_service.py`:
- lexical arm — `paper_chunks.search_document @@ websearch_to_tsquery`, ranked
  by `ts_rank`.
- semantic arm — query embedding vs `chunk_embeddings` cosine (`<=>`).
- **RRF fusion** (k=60), deduplicated to paper level, hydrated with
  title/year/authors/snippet.

`evidence_chat.answer_question` uses the hybrid retriever when a DSN is
configured and falls back to the in-memory matcher (sample corpus / no DB).
Generation goes through `deepseek_provider.get_llm_provider()` (mock / local
vLLM). Every answer carries auditable evidence.

## Trend forecasting (`/api/trends`)

`src/models/trends.py` (`make trend-model`) consumes the analysis assets and
produces `models/trends/{hot_keywords.csv, topic_trends.csv, trend_scores.json}`:
per-keyword growth/burst, a linear next-year forecast with a residual-based
uncertainty band (latest partial year excluded from the fit), and a composite
hotness score. Served by `backend/app/services/trends_service.py`.

> Note: keyword inputs carry extraction noise (journal/affiliation fragments,
> arXiv category codes). Improving keyword extraction in the analysis layer
> would directly improve trend quality.

## Recommendation (`/api/recommend`)

`src/models/recommend.py` (`make recommend-model`) builds `paper_embeddings`
(mean of chunk embeddings via pgvector `avg`) + ivfflat index.
`backend/app/services/recommend_service.py` fuses semantic similarity with
keyword overlap, author overlap, and recency, returning ranked papers with
explanation factors.

## Knowledge graph (`/api/graph`)

`src/models/graph_export.py` (`make graph-export`) exports pruned
client-friendly graphs (`graphs/{author,keyword,paper_topic}_graph.json` +
`graph_metrics.json`) — top-centrality nodes and the edges among them.
`backend/app/services/graph_service.py` serves overviews from the JSON and live
author ego-graphs from `coauthor_edges`.

## Build order

```bash
make postgres-schema && make pgvector-schema && make postgres-load   # serving layer
make embeddings                                                       # chunk vectors
make recommend-model                                                  # paper vectors
make trend-model graph-export                                         # forecast + graphs
# or: make agent-build   (embeddings + recommend + trend + graph)
```

## Client Boundary

The current client boundary is FastAPI + Go TUI. Web frontend code has been
removed; any future Web client should consume the same `/api/search`,
`/api/trends`, `/api/recommend`, `/api/graph`, and `/api/agent/stream`
contracts as a new scope.

## Not yet done / future

- GraphRAG (graph-augmented retrieval), cross-encoder reranking.
- Remote generation (DeepSeek / iFlytek Spark) — provider slot exists.
- Re-run on the final corpus once crawling completes:
  `make data-layer-refresh && make rag-chunks && make agent-build`.
