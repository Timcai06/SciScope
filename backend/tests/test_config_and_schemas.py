import pytest
from pydantic import ValidationError

from backend.app.core.config import _parse_bool, _parse_cors_origins
from backend.app.models.schemas import AgentRequest, ChatRequest, DashboardResponse


def test_parse_bool_accepts_common_true_values():
    assert _parse_bool("1", True) is True
    assert _parse_bool("yes", False) is True


def test_parse_bool_accepts_common_false_values():
    assert _parse_bool("0", True) is False


def test_parse_bool_rejects_unknown_values():
    with pytest.raises(ValueError, match="SCISCOPE_USE_MOCK_LLM"):
        _parse_bool("sometimes", True)


def test_parse_cors_origins_defaults_to_localhost():
    assert _parse_cors_origins(None) == []


def test_parse_cors_origins_splits_and_strips_values():
    assert _parse_cors_origins(" http://localhost:3000, https://example.com, ") == [
        "http://localhost:3000",
        "https://example.com",
    ]


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


def test_log_prompts_parse_error_names_env_var(monkeypatch):
    monkeypatch.setenv("SCISCOPE_LOG_PROMPTS", "sometimes")

    from backend.app.core.config import get_settings

    with pytest.raises(ValueError, match="Invalid SCISCOPE_LOG_PROMPTS value: 'sometimes'"):
        get_settings()


def test_integer_budget_parse_error_names_env_var(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_HISTORY_TURNS", "abc")

    from backend.app.core.config import get_settings

    with pytest.raises(ValueError, match="Invalid SCISCOPE_AGENT_MAX_HISTORY_TURNS value: 'abc'"):
        get_settings()


def test_chat_request_strips_question_whitespace():
    request = ChatRequest(question="  knowledge graph  ")

    assert request.question == "knowledge graph"


def test_chat_request_rejects_whitespace_only_question():
    with pytest.raises(ValidationError):
        ChatRequest(question="   ")


def test_agent_request_strips_question_whitespace():
    request = AgentRequest(question="  RAG  ")

    assert request.question == "RAG"


def test_agent_request_rejects_whitespace_only_question():
    with pytest.raises(ValidationError):
        AgentRequest(question="   ")


def test_agent_request_strips_session_id():
    request = AgentRequest(question="RAG", session_id="  tui-session  ")

    assert request.session_id == "tui-session"


def test_agent_request_accepts_retry_flag():
    request = AgentRequest(question="RAG", retry=True)

    assert request.retry is True


def test_dashboard_response_requires_explicit_year_range_shape():
    payload = {
        "total_papers": 1,
        "year_range": {"end": 2024},
        "publication_trend": [{"year": 2024, "count": 1}],
        "field_distribution": [{"field": "computer science", "count": 1}],
        "top_keywords": [{"keyword": "knowledge graph", "count": 1}],
        "collaboration_edges": [{"source": "A", "target": "B", "weight": 1}],
    }

    with pytest.raises(ValidationError):
        DashboardResponse(**payload)
