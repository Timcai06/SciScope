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


def test_agent_budget_rejects_oversized_history_content():
    request = AgentRequest(
        question="hello",
        history=[{"role": "user", "content": "x" * 11}],
        session_id="s",
    )

    violation = enforce_agent_budget(request, max_question_chars=10, max_history_turns=4)

    assert isinstance(violation, BudgetViolation)
    assert violation.code == "history_content_too_long"


def test_agent_budget_accepts_normal_request():
    request = AgentRequest(question="hello", history=[], session_id="s")

    violation = enforce_agent_budget(request, max_question_chars=100, max_history_turns=4)

    assert violation is None


def test_agent_stream_returns_budget_error(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_QUESTION_CHARS", "5")

    from fastapi.testclient import TestClient

    from backend.app.api import routes_agent
    from backend.app.main import create_app

    calls = []

    def fail_stream_agent(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("agent runtime should not be called for budget errors")

    monkeypatch.setattr(routes_agent, "_stream_agent", fail_stream_agent)

    with TestClient(create_app()) as client:
        response = client.post("/api/agent/stream", json={"question": "too long"})

    assert response.status_code == 200
    body = response.text
    assert '"type": "error"' in body
    assert "question_too_long" in body
    assert "data: [DONE]" in body
    assert calls == []


def test_agent_stream_sanitizes_production_runtime_errors(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "production")

    from fastapi.testclient import TestClient

    from backend.app.api import routes_agent
    from backend.app.main import create_app

    def leaking_stream_agent(*args, **kwargs):
        raise RuntimeError("secret provider token leaked")
        yield  # pragma: no cover

    monkeypatch.setattr(routes_agent, "_stream_agent", leaking_stream_agent)

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/agent/stream",
            json={"question": "hello"},
            headers={"x-request-id": "req-stream-1"},
        )

    assert response.status_code == 200
    assert "secret provider token" not in response.text
    assert "internal_error" in response.text
    assert "req-stream-1" in response.text
    assert "data: [DONE]" in response.text


def test_agent_stream_enforces_anonymous_rate_limit(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ANON_REQUESTS_PER_MINUTE", "1")

    from fastapi.testclient import TestClient

    from backend.app.api import routes_agent
    from backend.app.main import create_app

    def ok_stream_agent(*args, **kwargs):
        yield ("final", "ok")

    monkeypatch.setattr(routes_agent, "_stream_agent", ok_stream_agent)

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        first = client.post(
            "/api/agent/stream",
            json={"question": "hello"},
            headers={"x-forwarded-for": "203.0.113.10"},
        )
        second = client.post(
            "/api/agent/stream",
            json={"question": "hello again"},
            headers={"x-forwarded-for": "203.0.113.10"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "rate_limited" in second.text
    assert "data: [DONE]" in second.text


def test_agent_returns_budget_http_error(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_QUESTION_CHARS", "5")

    from fastapi.testclient import TestClient

    from backend.app.api import routes_agent
    from backend.app.main import create_app

    calls = []

    def fail_run_agent(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("agent runtime should not be called for budget errors")

    monkeypatch.setattr(routes_agent, "_run_agent", fail_run_agent)

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post("/api/agent", json={"question": "too long"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "question_too_long"
    assert calls == []
