# SciScope Hosted Backend v0.2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the packaged SciScope TUI usable immediately by connecting to a hosted Python/FastAPI backend by default while preserving local developer overrides.

**Architecture:** Keep the current Python FastAPI/LangGraph/RAG backend as the product runtime and package it for hosted deployment. Add production health/readiness, anonymous request budgets, deployment configuration, and TUI hosted/local/offline mode awareness without changing the existing SSE contract.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic/dataclasses, PostgreSQL + pgvector, DeepSeek API, Docker, Go Bubble Tea TUI, GoReleaser, Homebrew cask, Scoop manifest.

---

## File Structure

Create or modify these files:

- Create `backend/app/api/routes_health.py`: process health and production readiness endpoints.
- Create `backend/app/services/readiness_service.py`: dependency checks for DB tables, pgvector, retrieval state, and model provider config.
- Create `backend/app/core/budget.py`: anonymous request budget values and validation helpers.
- Create `backend/app/core/request_context.py`: request id/session id helpers used by logs and streamed errors.
- Modify `backend/app/main.py`: include health router and request context middleware.
- Modify `backend/app/core/config.py`: add production and hosted deployment settings.
- Modify `backend/app/api/routes_agent.py`: enforce request budget before streaming agent work.
- Modify `backend/tests/test_config_and_schemas.py`: settings tests.
- Create `backend/tests/test_health.py`: health/readiness endpoint tests.
- Create `backend/tests/test_agent_budget.py`: budget enforcement tests.
- Create `Dockerfile.backend`: deployable backend container.
- Create `.dockerignore`: small backend image context.
- Create `configs/hosted-backend.env.example`: production environment contract.
- Modify `Makefile`: add hosted backend Docker and smoke targets.
- Modify `tui/main.go`: hosted backend default and backend mode helpers.
- Modify `tui/doctor_demo.go`: hosted/local/offline doctor output.
- Modify `tui/render.go`: mode-specific connection recovery copy.
- Modify `tui/main_test.go`: hosted default, local override, doctor, and recovery tests.
- Modify `docs/runbook.md`: hosted backend operational path.
- Modify `docs/release/tui-homebrew.md`: normal user path no longer starts local backend.
- Modify `docs/release/tui-windows.md`: normal Windows path uses hosted backend.
- Modify `packaging/scoop/README.md`: package notes for hosted default.
- Modify `tui/.goreleaser.yaml`: v0.2.1 release comments only if needed.

Do not create user accounts, billing, public corpus mutation endpoints, or a web admin console in v0.2.1.

## Task 0: Record Deployment Decisions

**Files:**
- Create: `configs/hosted-backend.env.example`
- Modify: `docs/runbook.md`

- [ ] **Step 1: Write the deployment environment example**

Create `configs/hosted-backend.env.example`:

```bash
# SciScope hosted backend production environment.
SCISCOPE_APP_NAME=SciScope
SCISCOPE_ENV=production
SCISCOPE_USE_MOCK_LLM=false
SCISCOPE_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=example-server-secret
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
SCISCOPE_DB_DSN=postgresql://sciscope_app:example-password@db.sciscope.invalid:5432/sciscope
SCISCOPE_EMBEDDING_MODEL=intfloat/multilingual-e5-base
SCISCOPE_CORS_ORIGINS=
SCISCOPE_HOSTED_BACKEND_URL=https://api.sciscope.invalid
SCISCOPE_ANON_REQUESTS_PER_MINUTE=12
SCISCOPE_AGENT_MAX_HISTORY_TURNS=12
SCISCOPE_AGENT_MAX_TOOL_CALLS=8
SCISCOPE_AGENT_TIMEOUT_SECONDS=75
SCISCOPE_AGENT_MAX_QUESTION_CHARS=2000
SCISCOPE_LOG_PROMPTS=false
```

- [ ] **Step 2: Add deployment decision notes to the runbook**

Append this section to `docs/runbook.md`:

````markdown
## Hosted v0.2.1 Deployment Decisions

Before cutting v0.2.1, record the concrete hosted API base URL, hosting provider,
managed PostgreSQL/pgvector provider, and anonymous quota values. Use
`configs/hosted-backend.env.example` as the environment contract.

The packaged TUI must default to the hosted HTTPS API. Local development remains:

```bash
SCISCOPE_BACKEND=http://127.0.0.1:8000 sciscope-tui
```
````

- [ ] **Step 3: Verify documentation only**

Run: `git diff -- configs/hosted-backend.env.example docs/runbook.md`

Expected: only the new environment example and runbook section are shown.

- [ ] **Step 4: Commit**

```bash
git add configs/hosted-backend.env.example docs/runbook.md
git commit -m "docs: record hosted backend deployment contract"
```

## Task 1: Add Health And Readiness Endpoints

**Files:**
- Create: `backend/app/api/routes_health.py`
- Create: `backend/app/services/readiness_service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_health.py`

- [ ] **Step 1: Write failing health tests**

Create `backend/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_healthz_does_not_require_database(monkeypatch):
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "SciScope"}


def test_readyz_reports_missing_database(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"]["status"] == "missing"
    assert "SCISCOPE_DB_DSN" in body["checks"]["db"]["message"]
```

- [ ] **Step 2: Run the failing health tests**

Run: `python3 -m pytest backend/tests/test_health.py -v`

Expected: FAIL because `/healthz` and `/readyz` do not exist.

- [ ] **Step 3: Add readiness service**

Create `backend/app/services/readiness_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.config import Settings


@dataclass(frozen=True)
class ReadinessCheck:
    status: str
    message: str


def check_database_config(settings: Settings) -> ReadinessCheck:
    if not settings.db_dsn.strip():
        return ReadinessCheck("missing", "SCISCOPE_DB_DSN is required for hosted readiness")
    return ReadinessCheck("configured", "database DSN configured")


def check_model_config(settings: Settings) -> ReadinessCheck:
    if settings.use_mock_llm:
        return ReadinessCheck("mock", "mock LLM is enabled")
    if settings.llm_provider == "deepseek" and not settings.deepseek_api_key.strip():
        return ReadinessCheck("missing", "DEEPSEEK_API_KEY is required when DeepSeek is active")
    return ReadinessCheck("configured", f"{settings.llm_provider} provider configured")


def readiness_report(settings: Settings) -> tuple[int, dict[str, Any]]:
    checks = {
        "db": check_database_config(settings),
        "model": check_model_config(settings),
    }
    ready = all(check.status in {"configured"} for check in checks.values())
    body = {
        "status": "ready" if ready else "not_ready",
        "checks": {
            name: {"status": check.status, "message": check.message}
            for name, check in checks.items()
        },
    }
    return (200 if ready else 503), body
```

- [ ] **Step 4: Add health routes**

Create `backend/app/api/routes_health.py`:

```python
from fastapi import APIRouter, Response

from backend.app.core.config import get_settings
from backend.app.services.readiness_service import readiness_report

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name}


@router.get("/readyz")
def readyz(response: Response) -> dict[str, object]:
    status_code, body = readiness_report(get_settings())
    response.status_code = status_code
    return body
```

- [ ] **Step 5: Mount health routes**

Modify `backend/app/main.py` imports:

```python
from backend.app.api.routes_health import router as health_router
```

In `create_app()`, include it before other routers:

```python
    app.include_router(health_router)
```

- [ ] **Step 6: Run health tests**

Run: `python3 -m pytest backend/tests/test_health.py -v`

Expected: PASS.

- [ ] **Step 7: Run backend smoke tests**

Run: `python3 -m pytest backend/tests/test_api.py backend/tests/test_config_and_schemas.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes_health.py backend/app/services/readiness_service.py backend/app/main.py backend/tests/test_health.py
git commit -m "feat: add hosted backend health checks"
```

## Task 2: Add Production Settings And Request Budgets

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/core/budget.py`
- Test: `backend/tests/test_config_and_schemas.py`
- Test: `backend/tests/test_agent_budget.py`

- [ ] **Step 1: Add failing settings tests**

Append to `backend/tests/test_config_and_schemas.py`:

```python
def test_production_budget_settings(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    monkeypatch.setenv("SCISCOPE_ANON_REQUESTS_PER_MINUTE", "9")
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_HISTORY_TURNS", "5")
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_TOOL_CALLS", "4")
    monkeypatch.setenv("SCISCOPE_AGENT_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_QUESTION_CHARS", "700")
    monkeypatch.setenv("SCISCOPE_LOG_PROMPTS", "false")

    from backend.app.core.config import get_settings

    settings = get_settings()

    assert settings.env == "production"
    assert settings.anon_requests_per_minute == 9
    assert settings.agent_max_history_turns == 5
    assert settings.agent_max_tool_calls == 4
    assert settings.agent_timeout_seconds == 45
    assert settings.agent_max_question_chars == 700
    assert settings.log_prompts is False
```

Create `backend/tests/test_agent_budget.py`:

```python
from backend.app.core.budget import BudgetViolation, enforce_agent_budget
from backend.app.models.schemas import AgentRequest


def test_agent_budget_rejects_oversized_question():
    request = AgentRequest(question="x" * 11, history=[], session_id="s")

    violation = enforce_agent_budget(request, max_question_chars=10, max_history_turns=4)

    assert isinstance(violation, BudgetViolation)
    assert violation.code == "question_too_long"


def test_agent_budget_rejects_too_much_history():
    request = AgentRequest(
        question="hello",
        history=[{"role": "user", "content": "a"} for _ in range(5)],
        session_id="s",
    )

    violation = enforce_agent_budget(request, max_question_chars=100, max_history_turns=4)

    assert isinstance(violation, BudgetViolation)
    assert violation.code == "history_too_long"


def test_agent_budget_accepts_normal_request():
    request = AgentRequest(question="hello", history=[], session_id="s")

    violation = enforce_agent_budget(request, max_question_chars=100, max_history_turns=4)

    assert violation is None
```

- [ ] **Step 2: Run failing tests**

Run: `python3 -m pytest backend/tests/test_config_and_schemas.py::test_production_budget_settings backend/tests/test_agent_budget.py -v`

Expected: FAIL because the new settings and budget module do not exist.

- [ ] **Step 3: Extend settings**

Modify `backend/app/core/config.py` `Settings`:

```python
    anon_requests_per_minute: int
    agent_max_history_turns: int
    agent_max_tool_calls: int
    agent_timeout_seconds: int
    agent_max_question_chars: int
    log_prompts: bool
```

Add helper:

```python
def _parse_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"Expected positive integer, got {value!r}")
    return parsed
```

Add to `get_settings()`:

```python
        anon_requests_per_minute=_parse_int(os.getenv("SCISCOPE_ANON_REQUESTS_PER_MINUTE"), 12),
        agent_max_history_turns=_parse_int(os.getenv("SCISCOPE_AGENT_MAX_HISTORY_TURNS"), 12),
        agent_max_tool_calls=_parse_int(os.getenv("SCISCOPE_AGENT_MAX_TOOL_CALLS"), 8),
        agent_timeout_seconds=_parse_int(os.getenv("SCISCOPE_AGENT_TIMEOUT_SECONDS"), 75),
        agent_max_question_chars=_parse_int(os.getenv("SCISCOPE_AGENT_MAX_QUESTION_CHARS"), 2000),
        log_prompts=_parse_bool(os.getenv("SCISCOPE_LOG_PROMPTS"), default=False),
```

- [ ] **Step 4: Add budget module**

Create `backend/app/core/budget.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from backend.app.models.schemas import AgentRequest


@dataclass(frozen=True)
class BudgetViolation:
    code: str
    message: str


def enforce_agent_budget(
    request: AgentRequest,
    *,
    max_question_chars: int,
    max_history_turns: int,
) -> BudgetViolation | None:
    if len(request.question) > max_question_chars:
        return BudgetViolation(
            "question_too_long",
            f"question length exceeds {max_question_chars} characters",
        )
    if request.history and len(request.history) > max_history_turns:
        return BudgetViolation(
            "history_too_long",
            f"history exceeds {max_history_turns} turns",
        )
    return None
```

- [ ] **Step 5: Run budget/settings tests**

Run: `python3 -m pytest backend/tests/test_config_and_schemas.py::test_production_budget_settings backend/tests/test_agent_budget.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/core/budget.py backend/tests/test_config_and_schemas.py backend/tests/test_agent_budget.py
git commit -m "feat: add hosted request budgets"
```

## Task 3: Add Request Context And Safe Production Logging

**Files:**
- Create: `backend/app/core/request_context.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_health.py`

- [ ] **Step 1: Add failing request id test**

Append to `backend/tests/test_health.py`:

```python
def test_request_id_header_is_returned(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")
    client = TestClient(create_app())

    response = client.get("/healthz", headers={"x-request-id": "req-test-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-test-1"
```

- [ ] **Step 2: Run failing request id test**

Run: `python3 -m pytest backend/tests/test_health.py::test_request_id_header_is_returned -v`

Expected: FAIL because the app does not echo `x-request-id`.

- [ ] **Step 3: Add request context helpers**

Create `backend/app/core/request_context.py`:

```python
from __future__ import annotations

import contextvars
import uuid

from fastapi import Request

REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
SESSION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def request_id() -> str:
    current = REQUEST_ID.get()
    if current:
        return current
    generated = f"req-{uuid.uuid4().hex[:12]}"
    REQUEST_ID.set(generated)
    return generated


def session_id() -> str:
    return SESSION_ID.get()


def bind_request_context(request: Request) -> str:
    rid = request.headers.get("x-request-id", "").strip() or f"req-{uuid.uuid4().hex[:12]}"
    REQUEST_ID.set(rid)
    sid = request.headers.get("x-sciscope-session", "").strip()
    if sid:
        SESSION_ID.set(sid)
    return rid
```

- [ ] **Step 4: Add middleware in `backend/app/main.py`**

In `create_app()`, after `app = FastAPI(title=settings.app_name)`, add:

```python
    from backend.app.core.request_context import bind_request_context

    @app.middleware("http")
    async def request_context_middleware(request, call_next):
        request_id = bind_request_context(request)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
```

- [ ] **Step 5: Run health tests**

Run: `python3 -m pytest backend/tests/test_health.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/request_context.py backend/app/main.py backend/tests/test_health.py
git commit -m "feat: add hosted request context"
```

## Task 4: Enforce Agent Budget In SSE Route

**Files:**
- Modify: `backend/app/api/routes_agent.py`
- Test: `backend/tests/test_agent_budget.py`

- [ ] **Step 1: Add failing route test**

Append to `backend/tests/test_agent_budget.py`:

```python
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_agent_stream_returns_budget_error(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_QUESTION_CHARS", "5")
    client = TestClient(create_app())

    with client.stream(
        "POST",
        "/api/agent/stream",
        json={"question": "too long", "history": [], "session_id": "s"},
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "event: error" in body
    assert "question_too_long" in body
```

- [ ] **Step 2: Run failing route test**

Run: `python3 -m pytest backend/tests/test_agent_budget.py::test_agent_stream_returns_budget_error -v`

Expected: FAIL because `/api/agent/stream` does not enforce the new budget.

- [ ] **Step 3: Add budget check to `routes_agent.py`**

In `backend/app/api/routes_agent.py`, import:

```python
from backend.app.core.budget import enforce_agent_budget
from backend.app.core.config import get_settings
```

Before calling the agent stream, add:

```python
    settings = get_settings()
    violation = enforce_agent_budget(
        request,
        max_question_chars=settings.agent_max_question_chars,
        max_history_turns=settings.agent_max_history_turns,
    )
    if violation is not None:
        async def budget_error():
            yield event_parts("error", violation.message, {"code": violation.code})

        return StreamingResponse(budget_error(), media_type="text/event-stream")
```

Use the existing request variable name in the route. If the route currently calls
the parsed request `payload`, use `payload` in the snippet instead of `request`.

- [ ] **Step 4: Run route budget test**

Run: `python3 -m pytest backend/tests/test_agent_budget.py::test_agent_stream_returns_budget_error -v`

Expected: PASS.

- [ ] **Step 5: Run agent route tests**

Run: `python3 -m pytest backend/tests/test_agent_layer.py backend/tests/test_agent_runtime.py backend/tests/test_agent_budget.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes_agent.py backend/tests/test_agent_budget.py
git commit -m "feat: enforce hosted agent budgets"
```

## Task 5: Add Dockerized Backend Runtime

**Files:**
- Create: `Dockerfile.backend`
- Create: `.dockerignore`
- Modify: `Makefile`

- [ ] **Step 1: Add Dockerfile**

Create `Dockerfile.backend`:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r backend/requirements.txt

COPY backend backend
COPY src src
COPY data/sample data/sample
COPY configs configs

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Add Docker ignore**

Create `.dockerignore`:

```text
.git
.cache
.pytest_cache
__pycache__
*.pyc
tui/sciscope-tui
output
tmp
node_modules
```

- [ ] **Step 3: Add Makefile targets**

Add variables near existing backend variables:

```make
HOSTED_BACKEND_IMAGE ?= sciscope-backend:local
HOSTED_BACKEND_PORT ?= 8000
```

Add phony targets:

```make
.PHONY: backend-image backend-container-smoke hosted-smoke
```

Add target bodies:

```make
backend-image:
	docker build -f Dockerfile.backend -t $(HOSTED_BACKEND_IMAGE) .

backend-container-smoke: backend-image
	docker run --rm -p $(HOSTED_BACKEND_PORT):8000 --env-file configs/hosted-backend.env.example $(HOSTED_BACKEND_IMAGE) python -c "from backend.app.main import create_app; print(create_app().title)"

hosted-smoke:
	curl -fsS $(SCISCOPE_HOSTED_BACKEND_URL)/healthz
	curl -fsS $(SCISCOPE_HOSTED_BACKEND_URL)/readyz
```

- [ ] **Step 4: Run Dockerfile syntax check**

Run: `docker build -f Dockerfile.backend -t sciscope-backend:plan-check .`

Expected: image builds. If Docker is unavailable locally, record the exact error
and run this task on the deployment machine before release.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile.backend .dockerignore Makefile
git commit -m "build: add hosted backend container"
```

## Task 6: Add TUI Hosted Backend Mode

**Files:**
- Modify: `tui/main.go`
- Test: `tui/main_test.go`

- [ ] **Step 1: Add failing TUI backend mode tests**

Append to `tui/main_test.go`:

```go
func TestBackendURLDefaultsToHostedEndpoint(t *testing.T) {
	t.Setenv("SCISCOPE_BACKEND", "")
	t.Setenv("SCISCOPE_HOSTED_BACKEND", "https://api.example.test")

	got := backendURL()

	if got != "https://api.example.test" {
		t.Fatalf("backendURL() = %q, want hosted endpoint", got)
	}
}

func TestBackendURLLocalOverrideWins(t *testing.T) {
	t.Setenv("SCISCOPE_BACKEND", "http://127.0.0.1:8000/")
	t.Setenv("SCISCOPE_HOSTED_BACKEND", "https://api.example.test")

	got := backendURL()

	if got != "http://127.0.0.1:8000/" {
		t.Fatalf("backendURL() = %q, want explicit local override", got)
	}
}

func TestBackendModeLabelsHostedAndLocal(t *testing.T) {
	if got := backendMode("https://api.example.test"); got != "hosted" {
		t.Fatalf("backendMode(hosted) = %q", got)
	}
	if got := backendMode("http://127.0.0.1:8000"); got != "local" {
		t.Fatalf("backendMode(local) = %q", got)
	}
}
```

- [ ] **Step 2: Run failing TUI tests**

Run: `cd tui && GOCACHE=/Users/tim/Documents/数据要素/.cache/go-build go test ./... -run 'TestBackendURLDefaultsToHostedEndpoint|TestBackendURLLocalOverrideWins|TestBackendModeLabelsHostedAndLocal'`

Expected: FAIL because `SCISCOPE_HOSTED_BACKEND` and `backendMode` do not exist.

- [ ] **Step 3: Implement hosted backend helpers**

Modify `tui/main.go` around `backendURL()`:

```go
var defaultHostedBackendURL string

func hostedBackendURL() string {
	if v := strings.TrimSpace(os.Getenv("SCISCOPE_HOSTED_BACKEND")); v != "" {
		return strings.TrimRight(v, "/")
	}
	if strings.TrimSpace(defaultHostedBackendURL) != "" {
		return strings.TrimRight(defaultHostedBackendURL, "/")
	}
	return "http://127.0.0.1:8000"
}

func backendURL() string {
	if v := os.Getenv("SCISCOPE_BACKEND"); v != "" {
		return v
	}
	return hostedBackendURL()
}

func backendMode(url string) string {
	normalized := strings.ToLower(strings.TrimSpace(url))
	if strings.Contains(normalized, "127.0.0.1") || strings.Contains(normalized, "localhost") {
		return "local"
	}
	return "hosted"
}
```

The release build must inject the real hosted API base URL into
`defaultHostedBackendURL` with Go ldflags. Local development builds that do not
inject this value continue to fall back to `http://127.0.0.1:8000`.

- [ ] **Step 4: Run TUI backend mode tests**

Run: `cd tui && GOCACHE=/Users/tim/Documents/数据要素/.cache/go-build go test ./... -run 'TestBackendURLDefaultsToHostedEndpoint|TestBackendURLLocalOverrideWins|TestBackendModeLabelsHostedAndLocal'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tui/main.go tui/main_test.go
git commit -m "feat: default TUI to hosted backend"
```

## Task 7: Update TUI Doctor And Recovery Copy

**Files:**
- Modify: `tui/doctor_demo.go`
- Modify: `tui/render.go`
- Test: `tui/main_test.go`

- [ ] **Step 1: Add failing recovery tests**

Append to `tui/main_test.go`:

```go
func TestHostedBackendRecoveryDoesNotTellUserToRunMakeBackend(t *testing.T) {
	action := recoveryActionForBackend("https://api.example.test", "connection refused")

	if strings.Contains(action.Message, "make backend") || strings.Contains(action.Command, "make backend") {
		t.Fatalf("hosted recovery should not tell normal users to run make backend: %#v", action)
	}
	if !strings.Contains(action.Message, "/demo") {
		t.Fatalf("hosted recovery should offer demo fallback: %#v", action)
	}
}

func TestLocalBackendRecoveryStillMentionsMakeBackend(t *testing.T) {
	action := recoveryActionForBackend("http://127.0.0.1:8000", "connection refused")

	if action.Command != "make backend" {
		t.Fatalf("local recovery should keep developer command, got %#v", action)
	}
}
```

- [ ] **Step 2: Run failing recovery tests**

Run: `cd tui && GOCACHE=/Users/tim/Documents/数据要素/.cache/go-build go test ./... -run 'TestHostedBackendRecoveryDoesNotTellUserToRunMakeBackend|TestLocalBackendRecoveryStillMentionsMakeBackend'`

Expected: FAIL because `recoveryActionForBackend` does not exist.

- [ ] **Step 3: Implement mode-specific recovery**

In `tui/render.go`, add:

```go
func recoveryActionForBackend(baseURL, errText string) recovery {
	if backendMode(baseURL) == "local" {
		return recovery{
			Title:     "后端未连接",
			Command:   "make backend",
			Message:   "建议: 先运行 make backend, 然后输入 /retry 重试上一问。",
			Retryable: true,
		}
	}
	return recovery{
		Title:     "托管服务暂不可用",
		Command:   "/demo",
		Message:   "托管后端暂时不可达。可先输入 /demo 查看完整演示流, 或稍后 /retry。",
		Retryable: true,
	}
}
```

Modify existing backend connection failure branch in `recoveryAction` to call:

```go
return recoveryActionForBackend(backendURL(), s)
```

- [ ] **Step 4: Update doctor check copy**

In `tui/doctor_demo.go`, when backend is unreachable:

```go
if backendMode(backendURL()) == "local" {
	checks = append(checks, doctorCheck{"Backend", "warn", "not reachable; run make backend"})
} else {
	checks = append(checks, doctorCheck{"Backend", "warn", "hosted service unavailable; try /demo or retry later"})
}
```

- [ ] **Step 5: Run TUI recovery tests**

Run: `cd tui && GOCACHE=/Users/tim/Documents/数据要素/.cache/go-build go test ./... -run 'TestHostedBackendRecoveryDoesNotTellUserToRunMakeBackend|TestLocalBackendRecoveryStillMentionsMakeBackend|TestDoctorReportRendersProductChecks'`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tui/doctor_demo.go tui/render.go tui/main_test.go
git commit -m "feat: clarify hosted backend recovery"
```

## Task 8: Update Release Documentation And Package Text

**Files:**
- Modify: `docs/release/tui-homebrew.md`
- Modify: `docs/release/tui-windows.md`
- Modify: `packaging/scoop/README.md`
- Modify: `tui/.goreleaser.yaml`
- Modify: `packaging/scoop/bucket/sciscope-tui.json`

- [ ] **Step 1: Inject hosted backend URL in release builds**

In `tui/.goreleaser.yaml`, change the build `ldflags` entry to include both
version and hosted backend URL:

```yaml
    ldflags:
      - -s -w -X main.version={{ .Version }} -X main.defaultHostedBackendURL={{ .Env.SCISCOPE_HOSTED_BACKEND_URL }}
```

Release CI must set `SCISCOPE_HOSTED_BACKEND_URL` to the production HTTPS API
base URL before the `v0.2.1` tag is pushed.

- [ ] **Step 2: Update Homebrew caveats source**

In `tui/.goreleaser.yaml`, replace caveats with:

```yaml
    caveats: |
      直接连接托管科研智能体:
        sciscope-tui

      离线演示:
        sciscope-tui --demo

      开发者本地后端:
        SCISCOPE_BACKEND=http://127.0.0.1:8000 sciscope-tui
```

- [ ] **Step 3: Update Scoop notes**

In `packaging/scoop/bucket/sciscope-tui.json`, replace `notes` with:

```json
  "notes": [
    "Run sciscope-tui to connect to the hosted SciScope backend.",
    "Run sciscope-tui --demo for the offline golden demo.",
    "Developers can set SCISCOPE_BACKEND to use a local backend."
  ],
```

- [ ] **Step 4: Update release docs**

In `docs/release/tui-homebrew.md`, make the user install block:

```bash
brew tap Timcai06/sciscope
brew trust --cask timcai06/sciscope/sciscope-tui
brew install --cask sciscope-tui
sciscope-tui
```

In `docs/release/tui-windows.md`, make the Scoop path:

```powershell
scoop bucket add sciscope https://github.com/Timcai06/scoop-sciscope
scoop install sciscope-tui
sciscope-tui
```

In `packaging/scoop/README.md`, make the production attach text:

```powershell
sciscope-tui
```

and keep local override as a developer section:

```powershell
$env:SCISCOPE_BACKEND="http://127.0.0.1:8000"
sciscope-tui
```

- [ ] **Step 5: Verify docs no longer present local backend as normal user path**

Run: `rg -n "make backend && make llm|make backend.*sciscope-tui|run make backend" docs/release packaging/scoop tui/.goreleaser.yaml`

Expected: no matches in normal-user release sections. Matches in developer-only sections are acceptable if the surrounding text says developer/local.

- [ ] **Step 6: Verify GoReleaser config**

Run:

```bash
cd tui
SCISCOPE_HOSTED_BACKEND_URL=https://api.sciscope.invalid goreleaser check
cd ..
```

Expected: GoReleaser reports that the configuration file is valid.

- [ ] **Step 7: Commit**

```bash
git add docs/release/tui-homebrew.md docs/release/tui-windows.md packaging/scoop/README.md tui/.goreleaser.yaml packaging/scoop/bucket/sciscope-tui.json
git commit -m "docs: make hosted backend the package default"
```

## Task 9: End-To-End Verification And v0.2.1 Release

**Files:**
- Modify after release: `packaging/scoop/bucket/sciscope-tui.json`
- External repo after release: `Timcai06/scoop-sciscope`

- [ ] **Step 1: Run backend tests**

Run: `python3 -m pytest backend/tests -v`

Expected: PASS.

- [ ] **Step 2: Run TUI tests and build**

Run:

```bash
cd tui
GOCACHE=/Users/tim/Documents/数据要素/.cache/go-build go test ./...
GOCACHE=/Users/tim/Documents/数据要素/.cache/go-build go build ./...
cd ..
```

Expected: PASS and build exit code 0.

- [ ] **Step 3: Run hosted API smoke checks**

Run:

```bash
curl -fsS "$SCISCOPE_HOSTED_BACKEND_URL/healthz"
curl -fsS "$SCISCOPE_HOSTED_BACKEND_URL/readyz"
curl -fsS "$SCISCOPE_HOSTED_BACKEND_URL/api/ingest/status"
```

Expected: `/healthz` and `/readyz` return success JSON; ingest status returns corpus readiness JSON.

- [ ] **Step 4: Run one TUI doctor check against hosted backend**

Run:

```bash
SCISCOPE_HOSTED_BACKEND="$SCISCOPE_HOSTED_BACKEND_URL" make tui-doctor
```

Expected: doctor shows hosted backend reachable and does not ask normal users to run `make backend`.

- [ ] **Step 5: Build local v0.2.1 binary**

Run:

```bash
make tui-build TUI_VERSION=0.2.1
./tui/sciscope-tui --version
```

Expected: `sciscope-tui 0.2.1`.

Run a hosted URL injection check:

```bash
cd tui
GOCACHE=/Users/tim/Documents/数据要素/.cache/go-build go build -ldflags "-X main.version=0.2.1 -X main.defaultHostedBackendURL=$SCISCOPE_HOSTED_BACKEND_URL" -o sciscope-tui .
cd ..
```

Expected: build exit code 0.

- [ ] **Step 6: Commit any release metadata changes**

Run:

```bash
git status --short
git add README.md tui/README.md docs/release packaging/scoop tui/.goreleaser.yaml
git commit -m "release: prepare sciscope tui v0.2.1"
```

Expected: commit is created only if files changed.

- [ ] **Step 7: Push main and tag**

Run:

```bash
git push origin main
git tag v0.2.1
git push origin v0.2.1
```

Expected: release workflow starts for tag `v0.2.1`.

- [ ] **Step 8: Verify GitHub release assets**

Run:

```bash
curl -L https://github.com/Timcai06/SciScope/releases/download/v0.2.1/checksums.txt
```

Expected output contains:

```text
sciscope-tui_darwin_amd64.tar.gz
sciscope-tui_darwin_arm64.tar.gz
sciscope-tui_windows_amd64.zip
sciscope-tui_windows_arm64.zip
```

- [ ] **Step 9: Update Scoop manifest hashes**

Use the v0.2.1 checksum values to update `packaging/scoop/bucket/sciscope-tui.json`:

```json
  "version": "0.2.1",
```

and both Windows URLs:

```json
"https://github.com/Timcai06/SciScope/releases/download/v0.2.1/sciscope-tui_windows_amd64.zip"
"https://github.com/Timcai06/SciScope/releases/download/v0.2.1/sciscope-tui_windows_arm64.zip"
```

Run:

```bash
python3 -m json.tool packaging/scoop/bucket/sciscope-tui.json >/dev/null
git add packaging/scoop/bucket/sciscope-tui.json
git commit -m "release: update Scoop manifest for v0.2.1"
git push origin main
```

Expected: JSON parses and main is pushed.

- [ ] **Step 10: Update external Scoop bucket**

Run:

```bash
git clone https://github.com/Timcai06/scoop-sciscope.git /tmp/scoop-sciscope-v021
cp packaging/scoop/bucket/sciscope-tui.json /tmp/scoop-sciscope-v021/bucket/sciscope-tui.json
cd /tmp/scoop-sciscope-v021
python3 -m json.tool bucket/sciscope-tui.json >/dev/null
git add bucket/sciscope-tui.json
git commit -m "Update sciscope-tui to v0.2.1"
git push origin main
```

Expected: bucket repository main contains version `0.2.1`.

- [ ] **Step 11: Verify Homebrew and Scoop distribution**

Run:

```bash
brew update
brew info --cask Timcai06/sciscope/sciscope-tui
```

Expected: cask version is `0.2.1`.

Run:

```bash
curl -L https://raw.githubusercontent.com/Timcai06/scoop-sciscope/main/bucket/sciscope-tui.json
```

Expected: JSON contains `"version": "0.2.1"`.

## Self-Review Notes

- Spec coverage: the plan covers hosted default, Python/FastAPI retention,
  readiness, budget limits, DeepSeek server-side secret boundary, read-only DB
  posture, TUI hosted/local/offline behavior, Docker deployment, release docs,
  and brew/scoop release verification.
- Deferred by design: accounts, billing, public corpus writes, admin dashboard,
  backend rewrite, and multi-region operations.
- Required execution input before Task 5 release code: the real hosted HTTPS API
  base URL selected in Task 0.
