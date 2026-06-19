# SciScope Project Plan

## 1. Mission

SciScope is a research literature intelligence agent for scientific paper analysis. The project must deliver two primary outcomes required by the contest:

- A reproducible data analysis report covering literature distribution, keyword evolution, author collaboration networks, topic trends, and research insights.
- A runnable research agent system with Python code and model/index assets, supporting literature QA, trend prediction, paper recommendation, and knowledge graph queries.

AI Infra is an important differentiator, but it is a support layer. It must make the core analysis and agent capabilities reliable, reproducible, local-first, and compatible with DeepSeek or local vLLM.

## 2. Current State

Completed foundation:

- FastAPI backend with ingest status, dashboard overview, and evidence chat APIs.
- Next.js frontend foundation with dashboard and evidence chat.
- Deterministic sample corpus path using `data/sample/papers.sample.json`.
- Basic analytics: publication trends, field distribution, keyword counts, author collaboration edges.
- Mock LLM provider and OpenAI-compatible local provider path for vLLM/LM Studio.
- Makefile workflow, including backend/frontend/test commands and vLLM helpers.
- Multi-file LaTeX internal architecture document under `output/pdf/sciscope_design/`.

Current limitation:

- The repository currently has only 5 sample papers for smoke tests.
- The real 10k/50k contest-scale corpus has not been collected.
- No real analysis report assets, vector index, topic model, trend model, recommendation model, or graph query API have been built yet.

## 3. Strategic Principle

Do not crawl 50k papers directly into PostgreSQL as the first step.

Use a staged data pipeline:

1. Harvest public metadata into raw JSONL files.
2. Normalize and deduplicate into processed Parquet files.
3. Generate analysis assets, graph files, and model/index files.
4. Load structured data into PostgreSQL only after schema and quality checks are stable.
5. Serve APIs from PostgreSQL plus file-based/vector assets.

## 4. Target Architecture

```text
public sources
  -> raw JSONL
  -> normalized Parquet
  -> analysis assets
  -> PostgreSQL structured store
  -> FTS/vector/topic/graph indices
  -> FastAPI tools
  -> SciScope agent
  -> Next.js research workspace
```

## 5. Workstreams

- Data acquisition and compliance.
- Data normalization and asset generation.
- Analysis report pipeline.
- RAG, GraphRAG, recommendation, and trend models.
- API and agentic workflow.
- Frontend research workspace.
- AI Infra and runtime profiles.
- Final delivery, reproducibility, and acceptance.

## 6. Definition of Done

SciScope is complete when:

- A 10k sample corpus and later a 50k corpus can be collected or imported reproducibly.
- The system produces analysis assets for distribution, keyword evolution, author collaboration, topics, and trends.
- The research agent answers natural language questions with evidence from the corpus.
- The system supports trend prediction, paper recommendation, and knowledge graph queries.
- The frontend provides a polished research workspace rather than a demo page.
- The final package includes code, model/index files, report assets, runbook, and Makefile commands.
