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

1. **Chunk embeddings are partial.** The local embedder
   (`intfloat/multilingual-e5-base`, 768-dim) is downloaded to
   `models/embedder_local/multilingual-e5-base` (point `SCISCOPE_EMBEDDER_PATH`
   at it). Embedded so far: all `full_text` chunks (20,709) + ~18k mixed from an
   earlier partial run → ~38.5k vectors, `paper_embeddings` for 17,975 papers.
   The semantic arm and `/api/recommend` are live and cross-lingual (Chinese
   query → English paper) is verified. Full coverage (all 341k chunks) was
   deferred for thermal reasons — it is a ~4h MPS job. To finish later
   (resumable, skips done): `SCISCOPE_EMBEDDER_PATH=models/embedder_local/multilingual-e5-base make embeddings && make recommend-model`.
   Note from mainland China the HF download needs the mirror
   (`HF_ENDPOINT=https://hf-mirror.com`); `aria2c -c --file-allocation=none` is
   the reliable path (size = real bytes; verify a tail tensor is non-zero).
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
