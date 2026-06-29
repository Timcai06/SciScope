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
