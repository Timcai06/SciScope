# Status and Roadmap

## Where the project is now

### Data layer — done (exceeds brief)
- 6 sources, ~168k papers (brief asked ~50k), 5-year+ window.
- `data/analysis/` 30+ assets; `data/processed/papers_corpus.json` +
  `paper_chunks.jsonl` (~341k chunks, ~9.8k with full text).

### Analysis report (outcome ①) — substantially done
- Figures + PDF in `output/pdf/sciscope_data_report/`.

### Research-agent model (outcome ②) — built
- PostgreSQL + pgvector serving layer loaded (~160k papers / ~341k chunks /
  ~3.5M coauthor edges).
- Hybrid retrieval (FTS + vector + RRF) → `/api/search`, `/api/chat`.
- Trend forecast model → `/api/trends` (`models/trends/`).
- Recommendation model → `/api/recommend` (`paper_embeddings`).
- Knowledge-graph exports → `/api/graph` (`graphs/`).
- Frontend panels for all four.
- 90+ backend tests green.

See [01-agent-model-layer.md](01-agent-model-layer.md) for architecture.

## Known gaps / follow-ups

1. **Embeddings — full coverage (done).** Local embedder
   `intfloat/multilingual-e5-base` (768-dim) at
   `models/embedder_local/multilingual-e5-base` (`SCISCOPE_EMBEDDER_PATH`).
   Current: **226,434** chunk vectors — `title_abstract` 100% (197,639) and
   `full_text` 100% (20,663); `keywords` chunks intentionally not embedded
   (low value, covered by FTS). **`paper_embeddings` = 159,190 (every paper)**;
   the earlier CS-coverage bias (CS had only 87 vectors) is fixed (CS now 58,038).
   Semantic + cross-lingual retrieval and `/api/recommend` cover the whole corpus.
   Keyword chunks can be embedded later if desired but are not recommended.
2. **Keyword extraction noise** in the analysis layer leaks into trend rankings
   (journal/affiliation fragments, arXiv category codes). Cleaning extraction
   would improve trends and the keyword graph.
3. **Author overview graph is sparse** (top-centrality hubs rarely co-author);
   per-author ego graphs from the DB are richer.

## Parallel track: keep crawling

Crawling is decoupled from the model code. Keep running `make harvest-*`; at
checkpoints refresh and rebuild:

```bash
make data-layer-refresh   # analysis assets + processed corpus + report
make rag-chunks           # rebuild chunk assets
make postgres-refresh     # reload serving layer
make agent-build          # embeddings + recommend + trend + graph
```

## Next steps (priority order)

1. Finish the embedder download; run `make embeddings` then `make recommend-model`.
2. Smoke the full API surface against the real corpus (`make dev` + curl).
3. Improve keyword extraction quality in the analysis layer.
4. Wire local vLLM generation (`make dev-vllm`) for higher-quality answers.
5. Write the contest report (项目概述 / 解决方案 / 应用价值) for 格式规范 points.
