# Status and Roadmap

> **Forward-looking roadmap has moved.** The live product direction and next
> steps now live in [`docs/project/roadmap.md`](../docs/project/roadmap.md)
> (north star: `verify_claim` relatedness → entailment). This file is kept as the
> **delivered-state snapshot** and build history.

## Where the project is now (delivered & frozen)

### Data layer — done (exceeds brief), not expanding further
- 6 sources, ~168k papers (brief asked ~50k), 5-year+ window.
- `data/analysis/` 30+ assets; `data/processed/papers_corpus.json` +
  `paper_chunks.jsonl` (~367k chunk records, ~48k full-text chunks).
- Corpus is sufficient for the current north star; **stop harvesting** — new value
  is *derived* (stance/contradiction), not *collected*. See charter「数据方针」.

### Analysis report (outcome ①) — delivered
- Figures + PDF in `output/pdf/sciscope_data_report/`.

### Research-agent model (outcome ②) — delivered
- PostgreSQL + pgvector serving layer (~159k papers / ~367k chunks).
- Hybrid retrieval (FTS + vector + RRF) → `/api/search`, `/api/chat`.
- Trend forecast → `/api/trends` (`models/trends/`).
- Recommendation → `/api/recommend` (`paper_embeddings`).
- Knowledge-graph exports → `/api/graph` (`output/graphs/`).
- Agent: single LangGraph StateGraph over `/api/agent/stream`; Go TUI consumes SSE.
- Backend tests green (`make test-backend`).

See [01-agent-model-layer.md](01-agent-model-layer.md) for model-layer architecture.

## Known gaps / follow-ups (build-quality, not direction)

1. **Keyword extraction noise** in the analysis layer leaks into trend rankings
   (journal/affiliation fragments, arXiv category codes). Cleaning extraction
   would improve trends and the keyword graph.
2. **Author overview graph is sparse** (top-centrality hubs rarely co-author);
   per-author ego graphs from the DB are richer.

## Rebuild commands (when corpus or assets change)

```bash
make data-layer-refresh   # analysis assets + processed corpus + report
make rag-chunks           # rebuild chunk assets
make postgres-refresh     # reload serving layer
make agent-build          # embeddings + recommend + trend + graph
```

## Next direction

Product evolution is no longer "freeze for submission." It is the evidence-layer
north star — see [`docs/project/roadmap.md`](../docs/project/roadmap.md).
