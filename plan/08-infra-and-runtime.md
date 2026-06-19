# AI Infra and Runtime Plan

## 1. Role of AI Infra

AI Infra supports the contest deliverables. It should make the data analysis and research agent stable, reproducible, and impressive, but it must not replace the main tasks.

Main principle:

- M5 single-machine path must work first.
- PostgreSQL is introduced after data schema stabilizes.
- i5 is optional and never a critical dependency.
- DeepSeek is the final quality generation provider.
- Local vLLM is the offline/local fallback.

## 2. Runtime Profiles

Lite:

- Mock provider.
- sample or small processed corpus.
- no external LLM required.
- used for tests and quick smoke checks.

Local:

- local OpenAI-compatible provider.
- vLLM-Metal or LM Studio.
- used for offline demo and Infra credibility.

DeepSeek:

- real DeepSeek HTTP provider.
- used for final answer quality and Chinese report generation.

PostgreSQL:

- structured metadata serving.
- optional at 500/5k pilot.
- recommended for 10k and required for 50k.

## 3. PostgreSQL Plan

Do not use PostgreSQL as the first raw landing zone.

Use this order:

1. raw JSONL.
2. processed Parquet.
3. quality checks.
4. PostgreSQL load.
5. API serving.

Makefile targets:

```bash
make db-up
make db-migrate
make load-postgres
make db-status
```

Tables:

- papers.
- authors.
- paper_authors.
- keywords.
- paper_keywords.
- topics.
- paper_topics.
- chunks.
- crawl_runs.
- analysis_runs.

## 4. Makefile Roadmap

Current targets:

- `make install`
- `make backend`
- `make frontend`
- `make dev`
- `make dev-vllm`
- `make vllm-serve`
- `make vllm-smoke`
- `make test`
- `make smoke`
- `make clean`

Planned targets:

- `make harvest-sample`
- `make normalize`
- `make data-quality`
- `make analyze`
- `make index`
- `make report-assets`
- `make report`
- `make load-postgres`
- `make status`

## 5. DeepSeek Provider

Environment variables:

```text
SCISCOPE_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=
DEEPSEEK_BASE_URL=
```

Rules:

- If DeepSeek is unavailable, fall back to local or mock profile.
- Corpus-specific claims must still use local retrieved evidence.
- DeepSeek should not hallucinate citations.

## 6. Acceptance

Accepted when:

- `make test` passes.
- `make dev` runs mock profile.
- `make dev-vllm` runs with local OpenAI-compatible endpoint.
- DeepSeek profile returns evidence-grounded answers.
- PostgreSQL load can be repeated without duplicate records.
