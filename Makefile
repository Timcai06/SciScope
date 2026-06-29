SHELL := /bin/zsh

PROJECT_PYTHON := $(shell if [ -x /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python ]; then echo /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python; elif python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then command -v python3; else echo python3; fi)
PROJECT_TEST_PYTHON := $(shell if $(PROJECT_PYTHON) -c "import pytest" >/dev/null 2>&1; then echo $(PROJECT_PYTHON); elif python3 -c "import pytest" >/dev/null 2>&1; then command -v python3; else echo $(PROJECT_PYTHON); fi)
PYTHON ?= $(PROJECT_PYTHON)
TEST_PYTHON ?= $(PROJECT_TEST_PYTHON)
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
HOSTED_BACKEND_IMAGE ?= sciscope-backend:local
HOSTED_BACKEND_PORT ?= 8000
DATA_PATH ?= data/sample/papers.sample.json
HARVEST_SOURCE ?= openalex
HARVEST_LIMIT ?= 500
HARVEST_SOURCES ?= openalex arxiv pubmed pmc crossref doaj
RAW_SOURCE_DIR ?= data/raw
RAW_CANONICAL_DIR ?= data/raw_canonical
RAW_ARCHIVE_DIR ?= data/raw_archive
RAW_INVENTORY_PATH ?= data/raw_inventory.csv
RAW_MAX_YEAR ?= 2026
BALANCE_SOURCE ?= openalex
BALANCE_SOURCES ?= openalex arxiv pubmed pmc crossref doaj
BALANCE_YEAR ?= 2025
BALANCE_YEARS ?= 2022 2023 2024 2025
BALANCE_LIMIT ?= 9000
FULLTEXT_SOURCE ?= pmc
FULLTEXT_YEAR ?= 2025
FULLTEXT_YEARS ?= 2022 2023 2024 2025 2026
FULLTEXT_LIMIT ?= 3000
FULLTEXT_ENRICH_SOURCE ?= arxiv
FULLTEXT_ENRICH_YEARS ?= 2022,2023,2024,2025,2026
FULLTEXT_ENRICH_LIMIT ?= 200
FULLTEXT_ENRICH_SLEEP ?= 3
FULLTEXT_ENRICH_TIMEOUT ?= 20
FULLTEXT_ENRICH_MAX_BYTES ?= 4000000
FULLTEXT_ENRICH_MAX_ATTEMPTS ?=
FULLTEXT_ENRICH_CHECKPOINT_EVERY ?= 25
FULLTEXT_ENRICH_FIELD_FILTER ?=
FULLTEXT_ENRICH_RETRY_FAILED ?=
FULLTEXT_ENRICH_NO_BROWSER_FALLBACK ?=
FULLTEXT_ENRICH_STABLE_ONLY ?=
FULLTEXT_ARXIV_QBIO_LIMIT ?= 250
FULLTEXT_ARXIV_PHYSICS_LIMIT ?= 200
FULLTEXT_ARXIV_MATH_LIMIT ?= 180
FULLTEXT_PUBMED_BIOMED_LIMIT ?= 120
FULLTEXT_OPENALEX_MEDICINE_PROBE_LIMIT ?= 50
FULLTEXT_DOAJ_MEDICINE_PROBE_LIMIT ?= 50
FULLTEXT_PRIORITY_MAX_ATTEMPTS ?= 700
FULLTEXT_PROBE_MAX_ATTEMPTS ?= 300
RAW_PAPERS_PATH ?= data/raw/openalex/works_sample.jsonl
PROCESSED_PAPERS_PATH ?= data/processed/papers.json
PROCESSED_CORPUS_PATH ?= data/processed/papers_corpus.json
PROCESSED_CORPUS_SUMMARY_PATH ?= data/processed/papers_corpus.summary.json
ANALYSIS_OUTPUT_DIR ?= data/analysis
REPORT_ASSETS_DIR ?= output/assets/sciscope_data_report
PROJECT_REPORT_ASSETS_DIR ?= output/assets/sciscope_project_report
YEAR_BALANCE_TARGET ?= 10000
POSTGRES_DSN ?= postgresql://tim@localhost:5432/sciscope
EMBEDDING_MODEL ?= intfloat/multilingual-e5-base
EMBEDDER_PATH ?= models/embedder_local/multilingual-e5-base
EMBED_BATCH_SIZE ?= 256
TOPIC_COUNT ?= 40
EVAL_SAMPLE ?= 200
BACKFILL_SOURCE ?= crossref
BACKFILL_LIMIT ?= 2000
BACKFILL_MAILTO ?= cairentian932@gmail.com
RAG_CHUNKS_PATH ?= data/processed/paper_chunks.jsonl
RAG_CHUNKS_SUMMARY_PATH ?= data/processed/paper_chunks.summary.json
VLLM_HOST ?= 127.0.0.1
VLLM_PORT ?= 8001
VLLM_BASE_URL ?= http://$(VLLM_HOST):$(VLLM_PORT)/v1
VLLM_MODEL ?= mlx-community/Qwen2.5-7B-Instruct-4bit
VLLM_VENV ?= $(HOME)/.venv-vllm-metal
VLLM_MAX_MODEL_LEN ?= 8192
VLLM_EXTRA_ARGS ?=
LLM_LOCAL_DIR ?= models/llm_local/Qwen2.5-7B-Instruct-4bit
TUI_VERSION ?= dev
GO_BUILD_CACHE ?= $(CURDIR)/.cache/go-build

# Local secrets, gitignored. Put your key in .env.local as:  DEEPSEEK_API_KEY = sk-...
# Then `make backend` / `make dev` / `make tui` use DeepSeek by default.
-include .env.local

export SCISCOPE_APP_NAME ?= SciScope
export SCISCOPE_ENV ?= local
export SCISCOPE_DATA_PATH ?= $(DATA_PATH)
export SCISCOPE_CORS_ORIGINS ?=
export SCISCOPE_USE_MOCK_LLM ?= true
export SCISCOPE_LLM_PROVIDER ?= deepseek
export DEEPSEEK_API_KEY ?=
export DEEPSEEK_MODEL ?= deepseek-chat
export LOCAL_LLM_BASE_URL ?= $(VLLM_BASE_URL)
export LOCAL_LLM_MODEL ?= $(VLLM_MODEL)
# So `make backend` / `make dev` serve the real corpus (the agent/RAG need these);
# without them retrieval has no DB and every search returns "未检索到".
export SCISCOPE_DB_DSN ?= $(POSTGRES_DSN)
export SCISCOPE_EMBEDDER_PATH ?= $(EMBEDDER_PATH)
unexport VLLM_BASE_URL
unexport VLLM_EXTRA_ARGS
unexport VLLM_HOST
unexport VLLM_MAX_MODEL_LEN
unexport VLLM_MODEL
unexport VLLM_PORT
unexport VLLM_VENV

.PHONY: help install install-backend harvest-sample harvest-source harvest-all-sources harvest-year harvest-balanced-years harvest-fulltext-year harvest-fulltext-years fulltext-enrich-source fulltext-enrich-arxiv fulltext-enrich-arxiv-qbio fulltext-enrich-arxiv-physics fulltext-enrich-arxiv-math fulltext-enrich-pubmed-biomed fulltext-enrich-openalex-medicine-probe fulltext-enrich-doaj-medicine-probe fulltext-enrich-priority-fields fulltext-enrich-low-yield-probes raw-canonical raw-governance normalize normalize-source normalize-all-sources analysis-assets analysis-assets-all processed-corpus data-layer-audit data-layer-tonight data-layer-refresh rag-chunks postgres-schema postgres-load postgres-refresh pgvector-schema embeddings trend-model recommend-model graph-export agent-build full-rebuild tui tui-demo tui-doctor tui-export-last tui-build topic-model eval-retrieval eval-all backfill-abstracts dedupe-db report-figures project-report-figures data-report-pdf project-report-pdf submission-package report backend mcp dev dev-vllm llm llm-stop vllm-serve vllm-smoke test test-backend smoke agent-smoke clean
.PHONY: backend-image backend-container-smoke hosted-smoke

help:
	@echo "SciScope local commands"
	@echo ""
	@echo "  make install          Install backend Python deps"
	@echo "  make harvest-sample   Harvest public paper metadata into raw JSONL"
	@echo "  make harvest-source   Harvest one source into data/raw/<source>/<source>_<limit>.jsonl"
	@echo "  make harvest-all-sources Harvest $(HARVEST_LIMIT) records/source for configured public sources"
	@echo "  make harvest-year     Harvest one year into data/raw/<source>/<source>_<year>_<limit>.jsonl"
	@echo "  make harvest-balanced-years Harvest $(BALANCE_YEARS) by source/year for year balance"
	@echo "  make harvest-fulltext-years Harvest PMC full-text excerpts by publication year"
	@echo "  make fulltext-enrich-arxiv Enrich existing canonical arXiv partitions in place"
	@echo "  make fulltext-enrich-arxiv-qbio Enrich existing arXiv q-bio full text in place"
	@echo "  make fulltext-enrich-arxiv-physics Enrich existing arXiv physics full text in place"
	@echo "  make fulltext-enrich-arxiv-math Enrich existing arXiv math full text in place"
	@echo "  make fulltext-enrich-pubmed-biomed Enrich existing PubMed biomedicine full text in place"
	@echo "  make fulltext-enrich-priority-fields Run q-bio, physics, math, and PubMed biomed full-text enrichment"
	@echo "  make fulltext-enrich-low-yield-probes Probe OpenAlex/DOAJ medicine full-text yield"
	@echo "  make raw-canonical  Merge raw files into source/year canonical JSONL partitions"
	@echo "  make raw-governance Build canonical raw, archive old raw, and remove archive copy"
	@echo "                         API-key enhanced sources: semantic_scholar, core"
	@echo "  make normalize        Normalize raw JSONL into processed SciScope JSON"
	@echo "  make normalize-source Normalize one source into data/processed/<source>_<limit>.json"
	@echo "  make analysis-assets  Build report-ready analysis tables from raw JSONL"
	@echo "  make analysis-assets-all Build report tables from every JSONL under data/raw"
	@echo "  make processed-corpus Build merged processed corpus from analysis tables"
	@echo "  make data-layer-audit Audit year balance, text coverage, and RAG field readiness"
	@echo "  make data-layer-tonight Rebuild corpus plus data-layer readiness report"
	@echo "  make rag-chunks       Build chunk-level RAG assets from processed corpus"
	@echo "  make postgres-schema  Apply PostgreSQL schema to $(POSTGRES_DSN)"
	@echo "  make postgres-load    Load corpus/chunks into PostgreSQL"
	@echo "  make postgres-refresh Build chunks and load PostgreSQL service tables"
	@echo "  make report-figures   Build report-ready chart assets from data/analysis"
	@echo "  make project-report-figures Build product/system figures for the project report"
	@echo "  make data-report-pdf  Build the SciScope data analysis report PDF"
	@echo "  make project-report-pdf Build the project/system report PDF"
	@echo "  make submission-package Build the whitelist final submission zip"
	@echo "  make report           Rebuild analysis tables, report figures, and data PDF"
	@echo "  make backend          Start FastAPI backend on $(BACKEND_HOST):$(BACKEND_PORT)"
	@echo "  make dev              Start backend only (default development path)"
	@echo "  make tui-demo         Play the offline SciScope TUI golden demo flow"
	@echo "  make tui-doctor       Check TUI backend/LLM/session readiness"
	@echo "  make tui-export-last  Print the latest saved TUI Markdown session"
	@echo "  make vllm-serve       Start local vLLM-Metal server on $(VLLM_BASE_URL)"
	@echo "  make llm             Start local LLM (3B, offline) on $(VLLM_BASE_URL)"
	@echo "  make llm-stop        Stop the local LLM"
	@echo "  make dev-vllm         Start app using local vLLM/Metal OpenAI-compatible server"
	@echo "  make vllm-smoke       Check local vLLM OpenAI-compatible endpoint"
	@echo "  make test             Run backend tests"
	@echo "  make smoke            Check backend health endpoints with curl"
	@echo "  make agent-smoke      Check live agent skills, tools, and corpus size"
	@echo "  make clean            Remove generated local cache/build artifacts"
	@echo ""
	@echo "Backend docs:  http://$(BACKEND_HOST):$(BACKEND_PORT)/docs"

install: install-backend

install-backend:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r backend/requirements.txt

harvest-sample:
	$(PYTHON) -m src.harvest.cli harvest --source $(HARVEST_SOURCE) --limit $(HARVEST_LIMIT) --output $(RAW_PAPERS_PATH)

harvest-source:
	$(PYTHON) -m src.harvest.cli harvest --source $(HARVEST_SOURCE) --limit $(HARVEST_LIMIT)

harvest-all-sources:
	@for source in $(HARVEST_SOURCES); do \
		echo "==> harvesting $$source ($(HARVEST_LIMIT))"; \
		$(MAKE) harvest-source HARVEST_SOURCE=$$source HARVEST_LIMIT=$(HARVEST_LIMIT); \
	done

harvest-year:
	$(PYTHON) -m src.harvest.cli harvest-year --source $(BALANCE_SOURCE) --year $(BALANCE_YEAR) --limit $(BALANCE_LIMIT)

harvest-balanced-years:
	@for year in $(BALANCE_YEARS); do \
		for source in $(BALANCE_SOURCES); do \
			echo "==> harvesting $$source year=$$year limit=$(BALANCE_LIMIT)"; \
			$(MAKE) harvest-year BALANCE_SOURCE=$$source BALANCE_YEAR=$$year BALANCE_LIMIT=$(BALANCE_LIMIT); \
		done; \
	done

harvest-fulltext-year:
	$(PYTHON) -m src.harvest.cli harvest-year --source $(FULLTEXT_SOURCE) --year $(FULLTEXT_YEAR) --limit $(FULLTEXT_LIMIT)

harvest-fulltext-years:
	@for year in $(FULLTEXT_YEARS); do \
		echo "==> harvesting full text source=$(FULLTEXT_SOURCE) year=$$year limit=$(FULLTEXT_LIMIT)"; \
		$(MAKE) harvest-fulltext-year FULLTEXT_SOURCE=$(FULLTEXT_SOURCE) FULLTEXT_YEAR=$$year FULLTEXT_LIMIT=$(FULLTEXT_LIMIT); \
	done

fulltext-enrich-source:
	$(PYTHON) -m src.harvest.cli enrich-fulltext --canonical-dir $(RAW_CANONICAL_DIR) --source $(FULLTEXT_ENRICH_SOURCE) --years $(FULLTEXT_ENRICH_YEARS) --limit $(FULLTEXT_ENRICH_LIMIT) --sleep-seconds $(FULLTEXT_ENRICH_SLEEP) --timeout-seconds $(FULLTEXT_ENRICH_TIMEOUT) --max-download-bytes $(FULLTEXT_ENRICH_MAX_BYTES) --checkpoint-every $(FULLTEXT_ENRICH_CHECKPOINT_EVERY) $(if $(FULLTEXT_ENRICH_MAX_ATTEMPTS),--max-attempts $(FULLTEXT_ENRICH_MAX_ATTEMPTS),) $(if $(FULLTEXT_ENRICH_FIELD_FILTER),--field-filter "$(FULLTEXT_ENRICH_FIELD_FILTER)",) $(if $(FULLTEXT_ENRICH_RETRY_FAILED),--retry-failed,) $(if $(FULLTEXT_ENRICH_NO_BROWSER_FALLBACK),--no-browser-fallback,) $(if $(FULLTEXT_ENRICH_STABLE_ONLY),--stable-only,)

fulltext-enrich-arxiv:
	$(MAKE) fulltext-enrich-source FULLTEXT_ENRICH_SOURCE=arxiv

fulltext-enrich-arxiv-qbio:
	$(MAKE) fulltext-enrich-source FULLTEXT_ENRICH_SOURCE=arxiv FULLTEXT_ENRICH_YEARS=2022,2023,2024,2025,2026 FULLTEXT_ENRICH_LIMIT=$(FULLTEXT_ARXIV_QBIO_LIMIT) FULLTEXT_ENRICH_SLEEP=0.2 FULLTEXT_ENRICH_TIMEOUT=25 FULLTEXT_ENRICH_MAX_ATTEMPTS=$(FULLTEXT_PRIORITY_MAX_ATTEMPTS) FULLTEXT_ENRICH_CHECKPOINT_EVERY=20 FULLTEXT_ENRICH_FIELD_FILTER="q-bio"

fulltext-enrich-arxiv-physics:
	$(MAKE) fulltext-enrich-source FULLTEXT_ENRICH_SOURCE=arxiv FULLTEXT_ENRICH_YEARS=2022,2023,2024,2025,2026 FULLTEXT_ENRICH_LIMIT=$(FULLTEXT_ARXIV_PHYSICS_LIMIT) FULLTEXT_ENRICH_SLEEP=0.2 FULLTEXT_ENRICH_TIMEOUT=25 FULLTEXT_ENRICH_MAX_ATTEMPTS=$(FULLTEXT_PRIORITY_MAX_ATTEMPTS) FULLTEXT_ENRICH_CHECKPOINT_EVERY=20 FULLTEXT_ENRICH_FIELD_FILTER="physics"

fulltext-enrich-arxiv-math:
	$(MAKE) fulltext-enrich-source FULLTEXT_ENRICH_SOURCE=arxiv FULLTEXT_ENRICH_YEARS=2022,2023,2024,2025,2026 FULLTEXT_ENRICH_LIMIT=$(FULLTEXT_ARXIV_MATH_LIMIT) FULLTEXT_ENRICH_SLEEP=0.2 FULLTEXT_ENRICH_TIMEOUT=25 FULLTEXT_ENRICH_MAX_ATTEMPTS=650 FULLTEXT_ENRICH_CHECKPOINT_EVERY=20 FULLTEXT_ENRICH_FIELD_FILTER="math"

fulltext-enrich-pubmed-biomed:
	$(MAKE) fulltext-enrich-source FULLTEXT_ENRICH_SOURCE=pubmed FULLTEXT_ENRICH_YEARS=2022,2023,2024,2025,2026 FULLTEXT_ENRICH_LIMIT=$(FULLTEXT_PUBMED_BIOMED_LIMIT) FULLTEXT_ENRICH_SLEEP=0.2 FULLTEXT_ENRICH_TIMEOUT=25 FULLTEXT_ENRICH_STABLE_ONLY=1 FULLTEXT_ENRICH_MAX_ATTEMPTS=$(FULLTEXT_PRIORITY_MAX_ATTEMPTS) FULLTEXT_ENRICH_CHECKPOINT_EVERY=20 FULLTEXT_ENRICH_FIELD_FILTER="biomedicine"

fulltext-enrich-openalex-medicine-probe:
	$(MAKE) fulltext-enrich-source FULLTEXT_ENRICH_SOURCE=openalex FULLTEXT_ENRICH_YEARS=2022,2023,2024,2025,2026 FULLTEXT_ENRICH_LIMIT=$(FULLTEXT_OPENALEX_MEDICINE_PROBE_LIMIT) FULLTEXT_ENRICH_SLEEP=0.5 FULLTEXT_ENRICH_TIMEOUT=25 FULLTEXT_ENRICH_STABLE_ONLY=1 FULLTEXT_ENRICH_MAX_ATTEMPTS=$(FULLTEXT_PROBE_MAX_ATTEMPTS) FULLTEXT_ENRICH_CHECKPOINT_EVERY=10 FULLTEXT_ENRICH_FIELD_FILTER="medicine"

fulltext-enrich-doaj-medicine-probe:
	$(MAKE) fulltext-enrich-source FULLTEXT_ENRICH_SOURCE=doaj FULLTEXT_ENRICH_YEARS=2022,2023,2024,2025,2026 FULLTEXT_ENRICH_LIMIT=$(FULLTEXT_DOAJ_MEDICINE_PROBE_LIMIT) FULLTEXT_ENRICH_SLEEP=0.5 FULLTEXT_ENRICH_TIMEOUT=25 FULLTEXT_ENRICH_STABLE_ONLY=1 FULLTEXT_ENRICH_MAX_ATTEMPTS=$(FULLTEXT_PROBE_MAX_ATTEMPTS) FULLTEXT_ENRICH_CHECKPOINT_EVERY=10 FULLTEXT_ENRICH_FIELD_FILTER="medicine"

fulltext-enrich-priority-fields:
	$(MAKE) fulltext-enrich-arxiv-qbio
	$(MAKE) fulltext-enrich-arxiv-physics
	$(MAKE) fulltext-enrich-arxiv-math
	$(MAKE) fulltext-enrich-pubmed-biomed

fulltext-enrich-low-yield-probes:
	$(MAKE) fulltext-enrich-openalex-medicine-probe
	$(MAKE) fulltext-enrich-doaj-medicine-probe

raw-canonical:
	$(PYTHON) -m src.harvest.cli raw-canonical --raw-dir $(RAW_SOURCE_DIR) --canonical-dir $(RAW_CANONICAL_DIR) --inventory $(RAW_INVENTORY_PATH) --summary $(RAW_CANONICAL_DIR)/summary.json --max-year $(RAW_MAX_YEAR)

raw-governance:
	$(PYTHON) -m src.harvest.cli raw-canonical --raw-dir $(RAW_SOURCE_DIR) --canonical-dir $(RAW_CANONICAL_DIR) --inventory $(RAW_INVENTORY_PATH) --summary $(RAW_CANONICAL_DIR)/summary.json --max-year $(RAW_MAX_YEAR) --archive-old --archive-dir $(RAW_ARCHIVE_DIR) --delete-archive

normalize:
	$(PYTHON) -m src.harvest.cli normalize --input $(RAW_PAPERS_PATH) --output $(PROCESSED_PAPERS_PATH)

normalize-source:
	$(PYTHON) -m src.harvest.cli normalize --input data/raw/$(HARVEST_SOURCE)/$(HARVEST_SOURCE)_$(HARVEST_LIMIT).jsonl --output data/processed/$(HARVEST_SOURCE)_$(HARVEST_LIMIT).json

normalize-all-sources:
	@for source in $(HARVEST_SOURCES); do \
		echo "==> normalizing $$source ($(HARVEST_LIMIT))"; \
		$(MAKE) normalize-source HARVEST_SOURCE=$$source HARVEST_LIMIT=$(HARVEST_LIMIT); \
	done

analysis-assets:
	$(PYTHON) -m src.analysis.cli assets --raw-dir $(RAW_CANONICAL_DIR) --output-dir $(ANALYSIS_OUTPUT_DIR)

analysis-assets-all:
	$(PYTHON) -m src.analysis.cli assets --raw-dir $(RAW_CANONICAL_DIR) --output-dir $(ANALYSIS_OUTPUT_DIR)

processed-corpus:
	$(PYTHON) -m src.analysis.cli corpus --input $(ANALYSIS_OUTPUT_DIR)/papers_clean.json --output $(PROCESSED_CORPUS_PATH) --summary $(PROCESSED_CORPUS_SUMMARY_PATH)

data-layer-audit:
	$(PYTHON) -m src.analysis.cli readiness --papers $(ANALYSIS_OUTPUT_DIR)/papers_clean.json --output $(REPORT_ASSETS_DIR)/data_layer_readiness.json --target-per-year $(YEAR_BALANCE_TARGET)

data-layer-tonight: analysis-assets processed-corpus data-layer-audit

data-layer-refresh: analysis-assets-all processed-corpus data-layer-audit report-figures data-report-pdf

rag-chunks:
	$(PYTHON) -m src.infra.cli chunks --input $(PROCESSED_CORPUS_PATH) --output $(RAG_CHUNKS_PATH) --summary $(RAG_CHUNKS_SUMMARY_PATH)

postgres-schema:
	$(PYTHON) -m src.infra.cli schema --dsn $(POSTGRES_DSN) --file infra/postgres/schema.sql

postgres-load: rag-chunks
	$(PYTHON) -m src.infra.cli load-postgres --dsn $(POSTGRES_DSN) --papers $(PROCESSED_CORPUS_PATH) --chunks $(RAG_CHUNKS_PATH)

postgres-refresh: data-layer-refresh postgres-schema postgres-load

pgvector-schema:
	psql "$(POSTGRES_DSN)" -v ON_ERROR_STOP=1 -f infra/postgres/pgvector.sql

embeddings:
	$(PYTHON) -m src.models.build_embeddings --dsn $(POSTGRES_DSN) --chunks $(RAG_CHUNKS_PATH) --batch-size $(EMBED_BATCH_SIZE)

trend-model:
	$(PYTHON) -m src.models.trends --analysis-dir $(ANALYSIS_OUTPUT_DIR) --output-dir models/trends

recommend-model:
	$(PYTHON) -m src.models.recommend --dsn $(POSTGRES_DSN) --model $(EMBEDDING_MODEL)

graph-export:
	$(PYTHON) -m src.models.graph_export --analysis-dir $(ANALYSIS_OUTPUT_DIR) --output-dir output/graphs

# Full agent model-layer build (assumes corpus already loaded into PostgreSQL).
agent-build: embeddings recommend-model trend-model graph-export

# One-shot rebuild after data-layer enrichment (backfilled abstracts / full text):
# refresh analysis assets, reload DB (UPSERT), embed only NEW chunks (resume),
# rebuild recommend/trend/graph models, then refresh the data report (non-fatal,
# last). Run with SCISCOPE_EMBEDDER_PATH + SCISCOPE_EMBED_FP16 exported so the
# embedder loads locally instead of downloading.
full-rebuild:
	$(MAKE) analysis-assets-all
	$(MAKE) processed-corpus
	$(MAKE) rag-chunks
	$(MAKE) postgres-schema
	psql "$(POSTGRES_DSN)" -v ON_ERROR_STOP=1 -c "TRUNCATE paper_chunks CASCADE;"
	$(PYTHON) -m src.infra.cli load-postgres --dsn $(POSTGRES_DSN) --papers $(PROCESSED_CORPUS_PATH) --chunks $(RAG_CHUNKS_PATH)
	$(MAKE) embeddings
	$(MAKE) recommend-model
	$(MAKE) trend-model
	$(MAKE) graph-export
	-$(MAKE) report-figures
	-$(MAKE) data-report-pdf
	@echo "[full-rebuild] complete"

# Terminal agent client (Go / Bubble Tea / Charm) — release binaries use the
# hosted backend by default; developers can override with SCISCOPE_BACKEND.
tui:
	cd tui && GOCACHE=$(GO_BUILD_CACHE) go run .

# Offline golden demo: no backend, LLM, PostgreSQL, or network required.
tui-demo:
	cd tui && GOCACHE=$(GO_BUILD_CACHE) go run . demo

# Product readiness check for the distributable TUI client.
tui-doctor:
	cd tui && GOCACHE=$(GO_BUILD_CACHE) go run . doctor

# Print the latest saved TUI Markdown session to stdout.
tui-export-last:
	cd tui && GOCACHE=$(GO_BUILD_CACHE) go run . export --last

# Build the Go client to a single static binary (tui/sciscope-tui).
tui-build:
	cd tui && GOCACHE=$(GO_BUILD_CACHE) go build -ldflags "-X main.version=$(TUI_VERSION) -X main.defaultHostedBackendURL=$(SCISCOPE_HOSTED_BACKEND_URL)" -o sciscope-tui .

# Rebuild only the topic-model assets at finer granularity (default 40 topics).
topic-model:
	$(PYTHON) -m src.analysis.rebuild_topics --papers $(ANALYSIS_OUTPUT_DIR)/papers_clean.json --output-dir $(ANALYSIS_OUTPUT_DIR) --max-topics $(TOPIC_COUNT)

# Backfill missing abstracts from OpenAlex by DOI (canonical layer).
backfill-abstracts:
	$(PYTHON) -m src.harvest.abstract_backfill --source $(BACKFILL_SOURCE) --canonical-dir $(RAW_CANONICAL_DIR) --limit $(BACKFILL_LIMIT) --mailto $(BACKFILL_MAILTO)

# Deduplicate the loaded PostgreSQL corpus (dry run by default; add APPLY=1).
dedupe-db:
	$(PYTHON) -m src.infra.dedupe_db --dsn $(POSTGRES_DSN) $(if $(APPLY),--apply,)

# Self-retrieval evaluation of hybrid search (recall@k, MRR, latency).
eval-retrieval:
	SCISCOPE_DB_DSN=$(POSTGRES_DSN) SCISCOPE_EMBEDDER_PATH=$(EMBEDDER_PATH) $(PYTHON) -m evaluation.eval_retrieval --dsn $(POSTGRES_DSN) --sample $(EVAL_SAMPLE)

# Full evaluation evidence pack -> output/eval/ (retrieval + trend backtest + recommend).
eval-all:
	SCISCOPE_DB_DSN=$(POSTGRES_DSN) SCISCOPE_EMBEDDER_PATH=$(EMBEDDER_PATH) SCISCOPE_EMBED_FP16=1 $(PYTHON) -m evaluation.eval_all

report-figures:
	@mkdir -p .cache/matplotlib
	XDG_CACHE_HOME=$(CURDIR)/.cache MPLCONFIGDIR=$(CURDIR)/.cache/matplotlib $(PYTHON) -m src.analysis.cli figures --analysis-dir $(ANALYSIS_OUTPUT_DIR) --output-dir $(REPORT_ASSETS_DIR)

project-report-figures:
	@mkdir -p .cache/matplotlib
	XDG_CACHE_HOME=$(CURDIR)/.cache MPLCONFIGDIR=$(CURDIR)/.cache/matplotlib $(PYTHON) -m src.analysis.cli project-figures --analysis-dir $(ANALYSIS_OUTPUT_DIR) --processed-dir data/processed --eval-dir output/eval --output-dir $(PROJECT_REPORT_ASSETS_DIR)

data-report-pdf:
	python3 /Users/tim/.codex/plugins/cache/openai-bundled/latex/0.2.3/scripts/compile_latex.py $(CURDIR)/output/pdf/sciscope_data_report/main.tex --engine xelatex
	cp output/pdf/sciscope_data_report/main.pdf output/pdf/sciscope_data_report/sciscope_data_report.pdf
	rm -f output/pdf/sciscope_data_report/main.aux \
		output/pdf/sciscope_data_report/main.fdb_latexmk \
		output/pdf/sciscope_data_report/main.fls \
		output/pdf/sciscope_data_report/main.log \
		output/pdf/sciscope_data_report/main.out \
		output/pdf/sciscope_data_report/main.pdf \
		output/pdf/sciscope_data_report/main.synctex.gz \
		output/pdf/sciscope_data_report/main.toc \
		output/pdf/sciscope_data_report/main.xdv

project-report-pdf: project-report-figures
	python3 /Users/tim/.codex/plugins/cache/openai-bundled/latex/0.2.3/scripts/compile_latex.py $(CURDIR)/output/pdf/sciscope_project_report/main.tex --engine xelatex
	cp output/pdf/sciscope_project_report/main.pdf output/pdf/sciscope_project_report/sciscope_project_report.pdf
	rm -f output/pdf/sciscope_project_report/main.aux \
		output/pdf/sciscope_project_report/main.fdb_latexmk \
		output/pdf/sciscope_project_report/main.fls \
		output/pdf/sciscope_project_report/main.log \
		output/pdf/sciscope_project_report/main.out \
		output/pdf/sciscope_project_report/main.pdf \
		output/pdf/sciscope_project_report/main.synctex.gz \
		output/pdf/sciscope_project_report/main.toc \
		output/pdf/sciscope_project_report/main.xdv

submission-package: data-report-pdf project-report-pdf
	$(PYTHON) scripts/build_submission_package.py $(if $(INCLUDE_LARGE_MODELS),--include-large-models,)

report: analysis-assets processed-corpus report-figures data-report-pdf

backend:
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

backend-image:
	docker build -f Dockerfile.backend -t $(HOSTED_BACKEND_IMAGE) .

backend-container-smoke: backend-image
	cid=$$(docker run -d -p 127.0.0.1:$(HOSTED_BACKEND_PORT):8000 -e SCISCOPE_ENV=local -e SCISCOPE_USE_MOCK_LLM=true -e SCISCOPE_DB_DSN= $(HOSTED_BACKEND_IMAGE)); \
	trap 'docker rm -f $$cid >/dev/null' EXIT; \
	for i in {1..30}; do curl -fsS "http://127.0.0.1:$(HOSTED_BACKEND_PORT)/healthz" >/dev/null && break; sleep 1; done; \
	curl -fsS "http://127.0.0.1:$(HOSTED_BACKEND_PORT)/healthz"; \
	curl -fsS "http://127.0.0.1:$(HOSTED_BACKEND_PORT)/readyz"

hosted-smoke:
	test -n "$(SCISCOPE_HOSTED_BACKEND_URL)" || { echo "SCISCOPE_HOSTED_BACKEND_URL is required for hosted-smoke" >&2; exit 1; }
	curl -fsS "$(SCISCOPE_HOSTED_BACKEND_URL)/healthz"
	curl -fsS "$(SCISCOPE_HOSTED_BACKEND_URL)/readyz"

mcp:
	$(PYTHON) -m backend.app.mcp_server

dev:
	@echo "Starting SciScope backend..."
	@echo "Backend:  http://$(BACKEND_HOST):$(BACKEND_PORT)"
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

dev-vllm:
	@$(MAKE) dev SCISCOPE_USE_MOCK_LLM=false SCISCOPE_LLM_PROVIDER=vllm LOCAL_LLM_BASE_URL=$(VLLM_BASE_URL) LOCAL_LLM_MODEL=$(VLLM_MODEL)

llm:
	@echo "Starting local LLM (offline): $(LLM_LOCAL_DIR) on $(VLLM_BASE_URL)"
	@echo "Stop with Ctrl-C (or 'make llm-stop'). Then run 'make chat' in another shell."
	HF_HUB_OFFLINE=1 VLLM_HOST_IP=$(VLLM_HOST) $(VLLM_VENV)/bin/vllm serve $(LLM_LOCAL_DIR) \
		--host $(VLLM_HOST) --port $(VLLM_PORT) --max-model-len $(VLLM_MAX_MODEL_LEN) \
		--enable-auto-tool-choice --tool-call-parser hermes

llm-stop:
	@pkill -f "vllm serve" 2>/dev/null && echo "stopped local LLM" || echo "no local LLM running"

vllm-serve:
	@echo "Starting vLLM-Metal: $(VLLM_MODEL)"
	@echo "Endpoint: $(VLLM_BASE_URL)"
	@source $(VLLM_VENV)/bin/activate; \
	VLLM_HOST_IP=$(VLLM_HOST) \
	vllm serve $(VLLM_MODEL) \
		--host $(VLLM_HOST) \
		--port $(VLLM_PORT) \
		--max-model-len $(VLLM_MAX_MODEL_LEN) \
		$(VLLM_EXTRA_ARGS)

vllm-smoke:
	curl -fsS $(VLLM_BASE_URL)/models
	@echo ""
	curl -fsS -X POST $(VLLM_BASE_URL)/chat/completions \
		-H "Content-Type: application/json" \
		-d '{"model":"$(VLLM_MODEL)","messages":[{"role":"user","content":"用一句话解释RAG是什么"}],"temperature":0.2}'

test: test-backend

test-backend:
	$(TEST_PYTHON) -m pytest backend/tests -v

smoke:
	curl -fsS http://$(BACKEND_HOST):$(BACKEND_PORT)/api/ingest/status
	@echo ""
	curl -fsS http://$(BACKEND_HOST):$(BACKEND_PORT)/api/dashboard/overview >/dev/null
	@echo "dashboard overview ok"
	curl -fsS -X POST http://$(BACKEND_HOST):$(BACKEND_PORT)/api/chat \
		-H "Content-Type: application/json" \
		-d '{"question":"What does RAG improve?"}' >/dev/null
	@echo "chat ok"

agent-smoke:
	$(PYTHON) scripts/agent_smoke.py --base-url http://$(BACKEND_HOST):$(BACKEND_PORT)

clean:
	rm -rf .cache .pytest_cache tmp tui/dist tui/sciscope-tui
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name .DS_Store -type f -delete
