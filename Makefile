SHELL := /bin/zsh

PROJECT_PYTHON := $(shell if [ -x /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python ]; then echo /opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python; elif python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then command -v python3; else echo python3; fi)
PROJECT_TEST_PYTHON := $(shell if $(PROJECT_PYTHON) -c "import pytest" >/dev/null 2>&1; then echo $(PROJECT_PYTHON); elif python3 -c "import pytest" >/dev/null 2>&1; then command -v python3; else echo $(PROJECT_PYTHON); fi)
PYTHON ?= $(PROJECT_PYTHON)
TEST_PYTHON ?= $(PROJECT_TEST_PYTHON)
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000
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
RAW_PAPERS_PATH ?= data/raw/openalex/works_sample.jsonl
PROCESSED_PAPERS_PATH ?= data/processed/papers.json
PROCESSED_CORPUS_PATH ?= data/processed/papers_corpus.json
PROCESSED_CORPUS_SUMMARY_PATH ?= data/processed/papers_corpus.summary.json
ANALYSIS_OUTPUT_DIR ?= data/analysis
REPORT_ASSETS_DIR ?= output/assets/sciscope_data_report
YEAR_BALANCE_TARGET ?= 10000
POSTGRES_DSN ?= postgresql://tim@localhost:5432/sciscope
RAG_CHUNKS_PATH ?= data/processed/paper_chunks.jsonl
RAG_CHUNKS_SUMMARY_PATH ?= data/processed/paper_chunks.summary.json
VLLM_HOST ?= 127.0.0.1
VLLM_PORT ?= 8001
VLLM_BASE_URL ?= http://$(VLLM_HOST):$(VLLM_PORT)/v1
VLLM_MODEL ?= mlx-community/Qwen2.5-7B-Instruct-4bit
VLLM_VENV ?= $(HOME)/.venv-vllm-metal
VLLM_MAX_MODEL_LEN ?= 8192
VLLM_EXTRA_ARGS ?=

export SCISCOPE_APP_NAME ?= SciScope
export SCISCOPE_ENV ?= local
export SCISCOPE_DATA_PATH ?= $(DATA_PATH)
export SCISCOPE_CORS_ORIGINS ?= http://localhost:$(FRONTEND_PORT)
export SCISCOPE_USE_MOCK_LLM ?= true
export SCISCOPE_LLM_PROVIDER ?= deepseek
export LOCAL_LLM_BASE_URL ?= $(VLLM_BASE_URL)
export LOCAL_LLM_MODEL ?= $(VLLM_MODEL)
export NEXT_PUBLIC_SCISCOPE_API_BASE ?= http://$(BACKEND_HOST):$(BACKEND_PORT)
unexport VLLM_BASE_URL
unexport VLLM_EXTRA_ARGS
unexport VLLM_HOST
unexport VLLM_MAX_MODEL_LEN
unexport VLLM_MODEL
unexport VLLM_PORT
unexport VLLM_VENV

.PHONY: help install install-backend install-frontend harvest-sample harvest-source harvest-all-sources harvest-year harvest-balanced-years harvest-fulltext-year harvest-fulltext-years fulltext-enrich-source fulltext-enrich-arxiv raw-canonical raw-governance normalize normalize-source normalize-all-sources analysis-assets analysis-assets-all processed-corpus data-layer-audit data-layer-tonight data-layer-refresh rag-chunks postgres-schema postgres-load postgres-refresh report-figures data-report-pdf report backend frontend dev dev-vllm vllm-serve vllm-smoke test test-backend typecheck build smoke clean

help:
	@echo "SciScope local commands"
	@echo ""
	@echo "  make install          Install backend Python deps and frontend npm deps"
	@echo "  make harvest-sample   Harvest public paper metadata into raw JSONL"
	@echo "  make harvest-source   Harvest one source into data/raw/<source>/<source>_<limit>.jsonl"
	@echo "  make harvest-all-sources Harvest $(HARVEST_LIMIT) records/source for configured public sources"
	@echo "  make harvest-year     Harvest one year into data/raw/<source>/<source>_<year>_<limit>.jsonl"
	@echo "  make harvest-balanced-years Harvest $(BALANCE_YEARS) by source/year for year balance"
	@echo "  make harvest-fulltext-years Harvest PMC full-text excerpts by publication year"
	@echo "  make fulltext-enrich-arxiv Enrich existing canonical arXiv partitions in place"
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
	@echo "  make data-report-pdf  Build the SciScope data analysis report PDF"
	@echo "  make report           Rebuild analysis tables, report figures, and data PDF"
	@echo "  make backend          Start FastAPI backend on $(BACKEND_HOST):$(BACKEND_PORT)"
	@echo "  make frontend         Start Next.js frontend on localhost:$(FRONTEND_PORT)"
	@echo "  make dev              Start backend and frontend together"
	@echo "  make vllm-serve       Start local vLLM-Metal server on $(VLLM_BASE_URL)"
	@echo "  make dev-vllm         Start app using local vLLM/Metal OpenAI-compatible server"
	@echo "  make vllm-smoke       Check local vLLM OpenAI-compatible endpoint"
	@echo "  make test             Run backend tests and frontend typecheck/build"
	@echo "  make smoke            Check backend health endpoints with curl"
	@echo "  make clean            Remove generated frontend build artifacts"
	@echo ""
	@echo "Open frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "Backend docs:  http://$(BACKEND_HOST):$(BACKEND_PORT)/docs"

install: install-backend install-frontend

install-backend:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install fastapi uvicorn pydantic pandas numpy scikit-learn networkx matplotlib pytest httpx 'psycopg[binary]'

install-frontend:
	cd frontend && npm install

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

report-figures:
	@mkdir -p .cache/matplotlib
	XDG_CACHE_HOME=$(CURDIR)/.cache MPLCONFIGDIR=$(CURDIR)/.cache/matplotlib $(PYTHON) -m src.analysis.cli figures --analysis-dir $(ANALYSIS_OUTPUT_DIR) --output-dir $(REPORT_ASSETS_DIR)

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

report: analysis-assets processed-corpus report-figures data-report-pdf

backend:
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

frontend:
	cd frontend && npm run dev -- --hostname 0.0.0.0 --port $(FRONTEND_PORT)

dev:
	@echo "Starting SciScope backend and frontend..."
	@echo "Frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "Backend:  http://$(BACKEND_HOST):$(BACKEND_PORT)"
	@trap 'kill 0' INT TERM EXIT; \
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT) & \
	cd frontend && npm run dev -- --hostname 0.0.0.0 --port $(FRONTEND_PORT)

dev-vllm:
	@$(MAKE) dev SCISCOPE_USE_MOCK_LLM=false SCISCOPE_LLM_PROVIDER=vllm LOCAL_LLM_BASE_URL=$(VLLM_BASE_URL) LOCAL_LLM_MODEL=$(VLLM_MODEL)

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

test: test-backend typecheck build

test-backend:
	$(TEST_PYTHON) -m pytest backend/tests -v

typecheck:
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

smoke:
	curl -fsS http://$(BACKEND_HOST):$(BACKEND_PORT)/api/ingest/status
	@echo ""
	curl -fsS http://$(BACKEND_HOST):$(BACKEND_PORT)/api/dashboard/overview >/dev/null
	@echo "dashboard overview ok"
	curl -fsS -X POST http://$(BACKEND_HOST):$(BACKEND_PORT)/api/chat \
		-H "Content-Type: application/json" \
		-d '{"question":"What does RAG improve?"}' >/dev/null
	@echo "chat ok"

clean:
	rm -rf frontend/.next frontend/tsconfig.tsbuildinfo
