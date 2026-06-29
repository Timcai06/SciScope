# SciScope Hosted Backend v0.2.1 Design

## 1. Decision

SciScope v0.2.1 should ship a hosted backend so `brew install --cask sciscope-tui`
and `scoop install sciscope-tui` users can run `sciscope-tui` and ask real
questions without starting local ports.

The backend remains Python/FastAPI. We should not rewrite the agent backend in
Java, Go, C++, or TypeScript for this release.

## 2. Why Python Remains The Backend

The current backend already owns the product-critical runtime:

- FastAPI routes for dashboard, search, trends, recommendation, graph, ingest
  status, chat, and `/api/agent/stream`.
- LangGraph agent orchestration, tool calling, reflection, compaction, session
  memory, MCP integration, and specialist delegation.
- RAG services over PostgreSQL FTS, pgvector, RRF, corpus hydration, and fallback
  evidence chat behavior.
- DeepSeek provider abstraction and mock/local providers for tests.
- Data/report pipeline integration through existing Makefile targets.

The v0.2.1 problem is packaging and operations, not language capability. A
rewrite would delay product availability and duplicate working code.

Language boundaries:

- Python: hosted API, agent runtime, RAG, data services, model integration.
- Go: terminal client and local CLI distribution.
- TypeScript: future web console or account/admin UI, not v0.2.1 runtime.
- Java/C++: out of scope for the hosted agent backend.

## 3. Product Goal

Normal user path:

```bash
brew install --cask sciscope-tui
sciscope-tui
```

or:

```powershell
scoop bucket add sciscope https://github.com/Timcai06/scoop-sciscope
scoop install sciscope-tui
sciscope-tui
```

The installed TUI should connect to a stable HTTPS backend by default. Users
should not need `make backend`, PostgreSQL, pgvector, model files, or a local
LLM to evaluate the product.

Developer path remains:

```bash
SCISCOPE_BACKEND=http://127.0.0.1:8000 sciscope-tui
```

## 4. Proposed Architecture

```text
Go TUI package
  |
  | HTTPS + SSE
  v
Hosted FastAPI API
  |
  |-- /healthz
  |-- /readyz
  |-- /api/ingest/status
  |-- /api/agent/stream
  |-- /api/search, /api/trends, /api/recommend, /api/graph
  |
  |-- LangGraph agent runtime
  |-- Tool registry and validators
  |-- DeepSeek provider
  |-- Request budget and rate limiting
  |-- Structured logs and usage metrics
  v
Managed PostgreSQL + pgvector
  |
  |-- papers
  |-- paper_chunks
  |-- chunk_embeddings
  |-- paper_embeddings
  |-- trend/recommend/graph artifacts
```

The first hosted release is a read-only research intelligence API. Data
collection, corpus rebuilds, embeddings refresh, and report builds stay in the
offline Makefile pipeline.

## 5. Runtime Components

### 5.1 API Service

Package the existing `backend.app.main:app` in a Docker image.

Required production env:

- `SCISCOPE_ENV=production`
- `SCISCOPE_USE_MOCK_LLM=false`
- `SCISCOPE_LLM_PROVIDER=deepseek`
- `DEEPSEEK_API_KEY=<server secret>`
- `SCISCOPE_DB_DSN=<managed postgres dsn>`
- `SCISCOPE_EMBEDDING_MODEL=<deployed embedding model or precomputed mode>`
- `SCISCOPE_CORS_ORIGINS=<optional browser origins>`

The service should expose only API behavior needed by the TUI and future web
clients. It should not expose admin rebuild endpoints in v0.2.1.

### 5.2 Database

Use managed PostgreSQL with pgvector. The API should connect with a restricted
application role:

- read from corpus, chunk, embedding, trend, recommendation, and graph tables
- no schema migration permission
- no data deletion permission

Offline pipeline publishes data to the database through a maintainer-only path.
The public API remains read-only.

### 5.3 Model Provider

DeepSeek remains the default model family. The public TUI never receives model
keys. The hosted API owns all model credentials and enforces request budgets
before invoking DeepSeek.

### 5.4 Rate Limiting And Budgets

v0.2.1 can stay anonymous, but it must be bounded:

- IP/session rate limit.
- Max request body size.
- Max conversation history turns accepted from TUI.
- Max wall-clock duration per agent turn.
- Max tool calls per answer.
- Max final answer tokens.
- Per-request timeout around DeepSeek calls and DB retrieval.

If the budget is exceeded, the API streams a structured `error` event that the
TUI renders as a recovery card.

### 5.5 Observability

Minimum production observability:

- request id and session id in every log line
- endpoint, status, latency, stream duration
- model provider, model name, token usage when available
- tool call names and durations
- DB readiness failures
- rate-limit/budget denials

Do not log full user prompts by default in production. Keep a development flag
for verbose local logs only.

## 6. TUI Changes

`backendURL()` should prefer explicit env override, then hosted default:

```text
SCISCOPE_BACKEND set -> use it
else -> the v0.2.1 hosted HTTPS API base URL
```

The TUI should distinguish three modes:

- hosted product mode: default
- local developer mode: `SCISCOPE_BACKEND=http://127.0.0.1:8000`
- offline demo mode: `--demo` or explicit recovery choice

`doctor` should check:

- configured backend URL
- `/healthz`
- `/readyz`
- `/api/ingest/status`
- whether the app is using hosted or local mode

Connection failure copy should change from "run make backend" to:

- hosted mode: "hosted service is unavailable; try /demo or retry later"
- local mode: "run make backend, then /retry"

## 7. API Compatibility

Keep the current `/api/agent/stream` SSE contract stable:

- request: `question`, `history`, `session_id`, `retry`
- events: `plan`, `text`, `tool_call`, `tool_result`, `reflect`, `final`, `error`
- event `meta`: `runtime`, `node`, `phase`, `elapsed_ms`, `session_id`, `retry`

This protects the v0.2 TUI work and avoids a client rewrite.

New health endpoints:

- `GET /healthz`: process is alive; should not depend on DB or DeepSeek.
- `GET /readyz`: DB, required tables, pgvector/retrieval, and model provider
  configuration are ready enough for real agent answers.

## 8. Deployment Shape

Recommended v0.2.1 deployment:

- one Dockerized FastAPI service
- one managed PostgreSQL/pgvector database
- one HTTPS domain for the API
- environment secrets managed by the hosting platform
- no public write/admin endpoints

Good first deployment targets are platforms that can run a normal Dockerized
Python web service with long-lived SSE responses and outbound HTTPS to DeepSeek.
Avoid serverless-only environments that aggressively terminate streaming
responses or cold-start large Python dependencies.

## 9. Data Publication Flow

Keep data publication separate from the public runtime:

1. Maintainer runs offline data pipeline:
   - `processed-corpus`
   - `rag-chunks`
   - `postgres-load` or `postgres-refresh`
   - `embeddings`
   - `recommend-model`
   - `trend-model`
   - `graph-export`
2. Maintainer deploys or promotes the read-only database snapshot.
3. Hosted API `/readyz` verifies counts and required capabilities.
4. TUI release points to the hosted API.

This preserves reproducibility and avoids letting public clients mutate the
research corpus.

## 10. Release Plan

v0.2.1 should include:

- hosted API deployed and reachable by HTTPS
- TUI default backend changed to hosted URL
- local override preserved through `SCISCOPE_BACKEND`
- `doctor` updated for hosted/local/offline modes
- Homebrew caveats updated to "run sciscope-tui" as the normal path
- Scoop notes updated similarly
- release checks verifying:
  - `sciscope-tui --version`
  - `sciscope-tui doctor` against hosted backend
  - `/healthz`, `/readyz`, `/api/ingest/status`
  - one smoke streamed agent answer

## 11. Testing Strategy

Backend tests:

- unit tests for settings in production vs local mode
- `/healthz` independent of DB
- `/readyz` fails clearly when DB/provider is missing
- rate-limit/budget behavior returns structured errors
- SSE stream smoke test with mock provider

TUI tests:

- hosted URL is default when `SCISCOPE_BACKEND` is unset
- local URL is used when `SCISCOPE_BACKEND` is set
- hosted failure recovery does not tell normal users to run `make backend`
- local failure recovery still tells developers to run `make backend`
- doctor labels hosted/local/offline mode correctly

Release checks:

- Go tests and build
- backend tests
- Docker image starts and serves `/healthz`
- staging hosted API answers one fixed smoke question
- Homebrew and Scoop metadata point to v0.2.1 assets

## 12. Non-Goals For v0.2.1

- User accounts.
- Billing.
- Public data upload.
- Public corpus rebuild.
- Admin web dashboard.
- Rewriting backend language.
- Replacing PostgreSQL/pgvector.
- Full multi-region deployment.

These can come after the installed product has a trustworthy first-run
experience.

## 13. Open Decisions Before Implementation

1. Hosted API domain name.
2. Hosting provider.
3. Managed PostgreSQL/pgvector provider.
4. Initial anonymous quota values.
5. Whether production uses precomputed embeddings only or also computes query
   embeddings inside the API process.

Recommended defaults:

- Domain: a stable subdomain dedicated to API traffic.
- Provider: any Docker-friendly service with stable SSE support.
- Database: managed PostgreSQL with pgvector.
- Quota: conservative anonymous limits first.
- Embeddings: precompute corpus embeddings offline; compute only query
  embeddings at request time if needed.

## 14. Acceptance Criteria

v0.2.1 is ready when:

- A fresh user can install the TUI and ask one real question without running a
  local backend.
- The hosted backend streams evidence-grounded answers through the existing TUI.
- `SCISCOPE_BACKEND` still supports local development.
- Public runtime has no write access to corpus rebuild paths.
- Health/readiness checks make operational failure visible.
- Homebrew and Scoop package text no longer present local backend startup as the
  normal user path.
