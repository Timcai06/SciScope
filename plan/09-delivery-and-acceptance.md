# Delivery and Acceptance Plan

## 1. Final Deliverables

Required by contest:

- Data analysis report.
- Research agent model package.

SciScope delivery package:

```text
README.md
docs/runbook.md
output/pdf/sciscope_data_report/sciscope_data_report.pdf
output/assets/sciscope_data_report/
data/processed/
indices/
models/
graphs/
backend/
frontend/
src/
plan/
Makefile
```

## 2. Data Analysis Report Checklist

Must include:

- project background.
- data source and acquisition method.
- data quality overview.
- literature distribution analysis.
- keyword evolution.
- author collaboration network.
- topic structure and topic evolution.
- hotspot and trend prediction.
- system mapping: how the agent uses these assets.
- social and economic value.
- technical innovation.

## 3. Model Package Checklist

Must include:

- Python data pipeline.
- harvesting code.
- normalization code.
- analysis code.
- retrieval index.
- topic model.
- trend model.
- recommendation model.
- graph assets.
- LLM provider configuration.
- tests and run instructions.

## 4. System Checklist

Backend:

- ingest status.
- dashboard overview.
- paper search.
- chat.
- trends.
- recommendation.
- graph query.
- report draft.

Frontend:

- Overview.
- Ask.
- Trends.
- Graph.
- Recommend.
- Report Studio.

Infra:

- mock profile.
- local vLLM profile.
- DeepSeek profile.
- PostgreSQL profile.
- Makefile status checks.

## 5. Reproducibility Checklist

Evaluator should be able to run:

```bash
make install
make harvest-sample LIMIT=500
make normalize
make analyze
make index
make report-assets
make dev
make test
```

For local LLM:

```bash
make vllm-serve
make dev-vllm
```

For PostgreSQL:

```bash
make db-up
make load-postgres
make dev
```

## 6. Scoring Strategy

Social value:

- reduce literature review cost.
- help junior researchers and cross-disciplinary teams.
- make research trends and collaboration networks easier to understand.

Economic value:

- reduce manual literature intelligence labor.
- support university labs, R&D teams, technical strategy, and IP research.
- create reusable research intelligence workflow.

Technical innovation:

- RAG and GraphRAG.
- dynamic topic modeling.
- hotspot detection.
- evidence-grounded agentic workflow.
- local/DeepSeek hybrid model runtime.
- reproducible data and model assets.

Format quality:

- clean report.
- clear diagrams.
- one-command runbook.
- tests and smoke checks.
- polished frontend.

## 7. Final Acceptance

The project is accepted only when:

- At least 10k real public paper records are processed.
- The full 50k route is either completed or demonstrated by scalable pipeline design.
- Analysis report assets are generated from scripts.
- Chat, trend, recommendation, and graph APIs work on real data.
- Frontend presents real results, not placeholders.
- `make test` passes.
- A fresh user can follow the runbook to reproduce the system.
