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
    assert _parse_cors_origins(None) == ["http://localhost:3000"]


def test_parse_cors_origins_splits_and_strips_values():
    assert _parse_cors_origins(" http://localhost:3000, https://example.com, ") == [
        "http://localhost:3000",
        "https://example.com",
    ]


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
