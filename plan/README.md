# SciScope Plan Index

This directory contains the execution plan for the contest project:

`面向科技文献智能分析的科研智能体构建`

The plan is organized around the contest's two required outcomes:

- data analysis report.
- research agent model and runnable system.

## Documents

- [00-overview.md](00-overview.md): mission, current state, target architecture, and definition of done.
- [01-milestones.md](01-milestones.md): phased roadmap from data source confirmation to final delivery.
- [02-data-acquisition.md](02-data-acquisition.md): public data harvesting strategy and crawl plan.
- [03-data-assets-and-schema.md](03-data-assets-and-schema.md): canonical schema, processed assets, graph files, PostgreSQL tables.
- [04-analysis-report.md](04-analysis-report.md): report structure, required analyses, and report asset generation.
- [05-models-and-algorithms.md](05-models-and-algorithms.md): retrieval, topic, trend, recommendation, graph, and LLM provider model plan.
- [06-agent-and-api.md](06-agent-and-api.md): agentic workflow, agents, API roadmap, and response contracts.
- [07-frontend-workspace.md](07-frontend-workspace.md): product workspace views and frontend acceptance.
- [08-infra-and-runtime.md](08-infra-and-runtime.md): runtime profiles, PostgreSQL plan, DeepSeek/local vLLM strategy.
- [09-delivery-and-acceptance.md](09-delivery-and-acceptance.md): final deliverables, scoring strategy, and acceptance checklist.
- [10-next-sprint.md](10-next-sprint.md): immediate sprint to move from foundation slice to real public data.
- [11-tonight-data-layer-sprint.md](11-tonight-data-layer-sprint.md): immediate data-layer sprint for year balance, full-text enrichment, and RAG schema readiness.

## Immediate Next Step

Start with [11-tonight-data-layer-sprint.md](11-tonight-data-layer-sprint.md).

The next sprint goal is:

> Improve the 50k data asset layer by balancing non-2026 years, increasing evidence text coverage, and preparing RAG/Agent-oriented fields.

## Current Critical Decision

Do not crawl 50k records directly into PostgreSQL first.

Use:

```text
raw JSONL -> processed Parquet -> analysis/model assets -> PostgreSQL serving layer
```

This keeps the project reproducible and prevents early schema churn from corrupting the database.
