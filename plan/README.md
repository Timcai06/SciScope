# SciScope Plan Index

Execution plan for `面向科技文献智能分析的科研智能体构建`.

The contest requires two outcomes:

1. **数据分析报告** — literature distribution, keyword evolution, author
   collaboration networks. **Status: substantially complete** (see
   `data/analysis/`, `output/pdf/sciscope_data_report/`).
2. **科研智能体模型** — Python code + model files for literature QA, trend
   prediction, and paper recommendation. **Status: built** (this layer, see
   below).

## Current documents

- [00-status-and-roadmap.md](00-status-and-roadmap.md) — where the project is
  now and what remains.
- [01-agent-model-layer.md](01-agent-model-layer.md) — architecture of the
  research-agent model layer (service layer, embeddings, retrieval, trend,
  recommend, graph, APIs).

## Architecture decision (current)

Reproducible pipeline, PostgreSQL as the serving layer:

```text
raw JSONL -> processed corpus -> analysis/model assets
          -> PostgreSQL + pgvector serving layer -> FastAPI -> TUI/API
```

Web frontend code has been removed from the current delivery path; future Web
work should be treated as a new scope.

The research agent = Python code + reproducible model files:
- pgvector embeddings (`chunk_embeddings`, `paper_embeddings`)
- trend model files (`models/trends/`)
- recommendation model (`models/recommend/` + `paper_embeddings`)
- knowledge-graph exports (`graphs/`)
- local embedder (`models/embedder/`)

The LLM (local vLLM / LM Studio, OpenAI-compatible) is only the generation
layer; corpus-specific intelligence lives in the local models and indices.

## History

Earlier planning documents (foundation slice through the data-layer sprints)
are preserved in [archive/](archive/). They are historical and superseded by
the two documents above.
