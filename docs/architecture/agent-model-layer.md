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
  `passage:` prefixes). Cached under `models/embedder_local/`. Configurable via
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

## Landed after this document was written

- GraphRAG keyword-graph query expansion (`graphrag.py`) and local
  cross-encoder reranking (`bge-reranker-v2-m3`, optional) are now wired into
  retrieval (`retrieval_service.py`).
- Remote generation is live: DeepSeek is the hosted provider, local vLLM/LM
  Studio is the fallback (`backend/app/services/deepseek_provider.py`).
- Stance layer landed (roadmap steps 0–2): `verify_claim` judges per-evidence
  SUPPORT / CONTRADICT / NEUTRAL, persists to `claim_evidence_stance` and
  derives disputes via the `contradictions` view — the seed of the 科学争议地图.
  Current L3 plan (sentence-level evidence, calibration/rejection,
  qualification) is tracked in `docs/project/roadmap.md` and the frozen
  `docs/project/国赛目标说明书.md`.
- Data contracts moved from the former `data_pipeline/` package to
  `src/data_contracts/` (shared by backend runtime and `src.harvest`).
- Full rebuild: `make data-layer-refresh && make rag-chunks && make agent-build`.
