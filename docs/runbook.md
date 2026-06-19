# SciScope Runbook

This runbook covers local setup and verification for the SciScope foundation
slice: FastAPI backend APIs, the Next.js frontend, mock DeepSeek mode, and the
sample corpus.

## Requirements

- Python 3.11+
- Node.js 20+
- npm

## Source Documents

The original contest/source documents are stored at the repository root:

- `赛题.docx`
- `数据集.docx`

Treat these files as the source reference material for the project brief and
dataset description.

## Backend Setup

Run backend commands from the repository root.

The Makefile wraps the setup and development commands:

```bash
make install
make dev
```

`make dev` starts both services. Open the frontend at
`http://localhost:3000`; the backend API docs are at
`http://127.0.0.1:8000/docs`.

Manual backend setup is also available:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn pydantic pandas numpy scikit-learn networkx pytest httpx
```

Configure local environment values. The defaults work for the sample corpus and
mock LLM mode.

```bash
export SCISCOPE_APP_NAME=SciScope
export SCISCOPE_ENV=local
export SCISCOPE_DATA_PATH=outputs/sample/papers.sample.json
export SCISCOPE_CORS_ORIGINS=http://localhost:3000
export SCISCOPE_USE_MOCK_LLM=true
```

Start the backend:

```bash
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

## Backend Checks

Run tests from the repository root:

```bash
make test-backend
```

With the backend running on `127.0.0.1:8000`, verify the local APIs:

```bash
curl http://127.0.0.1:8000/api/ingest/status
curl http://127.0.0.1:8000/api/dashboard/overview
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"What does RAG improve?"}'
```

Expected results:

- Ingest status returns `{"status":"ready","papers":...}`.
- Dashboard overview returns totals, year range, trend, field distribution,
  keywords, and collaboration edges.
- Chat returns an `answer`, `evidence`, and `confidence`.

## Frontend Setup

Run frontend commands from `frontend`.

```bash
cd frontend
npm install
export NEXT_PUBLIC_SCISCOPE_API_BASE=http://localhost:8000
npm run typecheck
npm run build
npm run dev
```

Open the app at:

```text
http://localhost:3000
```

The frontend reads `NEXT_PUBLIC_SCISCOPE_API_BASE` at build/runtime to call the
FastAPI backend. Use `http://localhost:8000` for the standard local backend.

From the repository root, the equivalent Makefile commands are:

```bash
make frontend
make typecheck
make build
```

## DeepSeek Configuration

The default development path uses the deterministic mock provider. Keep mock
mode enabled for repeatable tests:

```bash
export SCISCOPE_USE_MOCK_LLM=true
```

## Local vLLM-Metal Configuration

For local model generation on Apple Silicon, run a vLLM-Metal OpenAI-compatible
server separately, then start SciScope with the local provider.

Recommended first model:

```text
mlx-community/Qwen2.5-7B-Instruct-4bit
```

Start the local model server on a port that does not conflict with the SciScope
backend:

```bash
vllm serve mlx-community/Qwen2.5-7B-Instruct-4bit \
  --host 127.0.0.1 \
  --port 8001
```

Then start the full SciScope app against that local server:

```bash
make dev-vllm
```

Equivalent manual environment:

```bash
export SCISCOPE_USE_MOCK_LLM=false
export SCISCOPE_LLM_PROVIDER=vllm
export LOCAL_LLM_BASE_URL=http://127.0.0.1:8001/v1
export LOCAL_LLM_MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit
make dev
```

The same provider also works with LM Studio or another OpenAI-compatible local
server by changing `SCISCOPE_LLM_PROVIDER`, `LOCAL_LLM_BASE_URL`, and
`LOCAL_LLM_MODEL`.

## DeepSeek Configuration

Real DeepSeek HTTP integration is intentionally deferred to a later
implementation slice. Keep `SCISCOPE_LLM_PROVIDER=deepseek` only for mock mode
or configuration/error-path tests until that provider is implemented.

When real integration lands, it will use environment configuration for the API
key, model name, and optional compatible base URL.

## Webpack Workaround

The frontend `dev` and `build` scripts use webpack:

```json
"dev": "next dev --webpack",
"build": "next build --webpack"
```

This is intentional. Turbopack had issues in this repository path because it
contains Chinese characters (`数据要素`). Revisit the workaround after a
Next/Turbopack upgrade or after moving the repository to an ASCII-only path.

## Local Verification Checklist

Use this checklist before handing off foundation changes:

```bash
make test
```

For full manual verification, run the backend and frontend together, open
`http://localhost:3000`, confirm the dashboard loads, and submit a chat question
that returns evidence from the sample corpus.
