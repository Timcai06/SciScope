SHELL := /bin/zsh

PYTHON ?= python3
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000
DATA_PATH ?= outputs/sample/papers.sample.json

export SCISCOPE_APP_NAME ?= SciScope
export SCISCOPE_ENV ?= local
export SCISCOPE_DATA_PATH ?= $(DATA_PATH)
export SCISCOPE_CORS_ORIGINS ?= http://localhost:$(FRONTEND_PORT)
export SCISCOPE_USE_MOCK_LLM ?= true
export NEXT_PUBLIC_SCISCOPE_API_BASE ?= http://$(BACKEND_HOST):$(BACKEND_PORT)

.PHONY: help install install-backend install-frontend backend frontend dev test test-backend typecheck build smoke clean

help:
	@echo "SciScope local commands"
	@echo ""
	@echo "  make install          Install backend Python deps and frontend npm deps"
	@echo "  make backend          Start FastAPI backend on $(BACKEND_HOST):$(BACKEND_PORT)"
	@echo "  make frontend         Start Next.js frontend on localhost:$(FRONTEND_PORT)"
	@echo "  make dev              Start backend and frontend together"
	@echo "  make test             Run backend tests and frontend typecheck/build"
	@echo "  make smoke            Check backend health endpoints with curl"
	@echo "  make clean            Remove generated frontend build artifacts"
	@echo ""
	@echo "Open frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "Backend docs:  http://$(BACKEND_HOST):$(BACKEND_PORT)/docs"

install: install-backend install-frontend

install-backend:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install fastapi uvicorn pydantic pandas numpy scikit-learn networkx pytest httpx

install-frontend:
	cd frontend && npm install

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

test: test-backend typecheck build

test-backend:
	$(PYTHON) -m pytest backend/tests -v

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
