from __future__ import annotations

import time
from dataclasses import dataclass

from backend.app.models.schemas import AgentRequest


@dataclass(frozen=True)
class BudgetViolation:
    code: str
    message: str


_RATE_LIMIT_BUCKETS: dict[str, tuple[int, int]] = {}


def enforce_anonymous_rate_limit(
    key: str,
    *,
    requests_per_minute: int,
    now: float | None = None,
) -> BudgetViolation | None:
    """In-process anonymous budget guard for the hosted API edge."""
    current = time.time() if now is None else now
    window = int(current // 60)
    bucket_key = key or "anonymous"
    bucket_window, count = _RATE_LIMIT_BUCKETS.get(bucket_key, (window, 0))
    if bucket_window != window:
        bucket_window, count = window, 0
    count += 1
    _RATE_LIMIT_BUCKETS[bucket_key] = (bucket_window, count)
    if count > requests_per_minute:
        return BudgetViolation(
            "rate_limited",
            f"anonymous request budget exceeds {requests_per_minute} requests per minute",
        )
    return None


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
    for turn in request.history:
        if len(turn.content) > max_question_chars:
            return BudgetViolation(
                "history_content_too_long",
                f"history turn length exceeds {max_question_chars} characters",
            )
    return None
