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
