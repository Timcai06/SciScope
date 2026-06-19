# Milestones

## Phase 0: Data Source Confirmation

Goal: decide where the contest corpus comes from and make the harvesting path legal and reproducible.

Tasks:

- Confirm public sources: OpenAlex, arXiv, PubMed, Crossref as needed.
- Define topic queries for computer science, biomedicine, and materials science.
- Define crawl rules, API keys, rate limits, and attribution requirements.
- Create `data/raw/`, `data/processed/`, `indices/`, `models/`, `graphs/`, and `reports/assets/`.

Acceptance:

- `plan/02-data-acquisition.md` is implemented as CLI tasks.
- A 500-record pilot crawl can be reproduced.

## Phase 1: 500-Paper Pilot

Goal: validate schema, normalization, deduplication, and end-to-end analysis.

Tasks:

- Implement `make harvest-sample LIMIT=500`.
- Implement `make normalize`.
- Generate `papers.parquet` and a data quality report.
- Run basic analytics on real harvested data.
- Verify `/api/dashboard/overview` uses real processed data.

Acceptance:

- At least 500 valid paper records.
- Fields normalized: paper id, title, abstract, authors, year, keywords, field, source.
- Basic dashboard works on real data.

## Phase 2: 5k Dataset

Goal: move from smoke tests to meaningful analysis.

Tasks:

- Expand queries across three domains.
- Generate keyword-year matrix.
- Generate author collaboration graph.
- Add first report assets.
- Add `/api/trends`.

Acceptance:

- 5k papers.
- Keyword evolution and author network assets are generated.
- Frontend can show real trend and collaboration data.

## Phase 3: 10k Contest Sample Scale

Goal: match the stated sample scale and build the first complete product slice.

Tasks:

- Build FTS and vector indices.
- Build topic model.
- Build recommendation model.
- Add `/api/recommend`, `/api/graph`, and `/api/topics`.
- Generate first complete analysis report draft.

Acceptance:

- 10k papers.
- QA, trend, recommendation, and graph APIs are available.
- Internal report assets are reproducible from Makefile.

## Phase 4: 50k Full Scale

Goal: reach final-scale corpus and optimize performance.

Tasks:

- Expand harvesting to 50k with retry and checkpointing.
- Load structured records into PostgreSQL.
- Add query indexes.
- Optimize API latency.
- Downsample graph views for frontend.

Acceptance:

- 50k papers imported.
- API responses remain usable for dashboard, search, trends, and recommendations.
- Re-running the pipeline does not duplicate papers.

## Phase 5: Final Product and Delivery

Goal: produce final contest-ready artifacts.

Tasks:

- Final data analysis report.
- Final model/index assets.
- Final frontend polish.
- DeepSeek provider integration.
- Runbook and reproducibility checklist.

Acceptance:

- `make test` passes.
- `make smoke` passes.
- `make report` produces final report assets.
- A fresh evaluator can install, configure, run, and reproduce the core outputs.
