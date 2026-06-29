from __future__ import annotations

import time
from dataclasses import dataclass

from backend.app.models.schemas import AgentRequest, ChatRequest


@dataclass(frozen=True)
class BudgetViolation:
    code: str
    message: str


_RATE_LIMIT_BUCKETS: dict[str, tuple[int, int]] = {}
_MAX_RATE_LIMIT_BUCKETS = 4096


def _prune_rate_limit_buckets(current_window: int) -> None:
    expired = [key for key, (window, _count) in _RATE_LIMIT_BUCKETS.items() if window != current_window]
    for key in expired:
        _RATE_LIMIT_BUCKETS.pop(key, None)
    while len(_RATE_LIMIT_BUCKETS) > _MAX_RATE_LIMIT_BUCKETS:
        oldest = next(iter(_RATE_LIMIT_BUCKETS))
        _RATE_LIMIT_BUCKETS.pop(oldest, None)


def enforce_anonymous_rate_limit(
    key: str,
    *,
    requests_per_minute: int,
    now: float | None = None,
) -> BudgetViolation | None:
    """In-process anonymous budget guard for the hosted API edge."""
    current = time.time() if now is None else now
    window = int(current // 60)
    _prune_rate_limit_buckets(window)
    bucket_key = key or "anonymous"
    bucket_window, count = _RATE_LIMIT_BUCKETS.get(bucket_key, (window, 0))
    if bucket_window != window:
        bucket_window, count = window, 0
    count += 1
    _RATE_LIMIT_BUCKETS[bucket_key] = (bucket_window, count)
    _prune_rate_limit_buckets(window)
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


def enforce_chat_budget(
    request: ChatRequest,
    *,
    max_question_chars: int,
    max_history_turns: int,
) -> BudgetViolation | None:
    """Apply the same hosted cost guard to evidence chat requests.

    ``/api/chat`` can call the configured LLM directly, so it needs the same
    public-edge budget contract as the agent route even though it does not run
    the full tool loop.
    """
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
