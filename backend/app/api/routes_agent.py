"""Agentic assistant API — the SciScope agent loop over HTTP.

Mirrors OpenCode's server/client split: the agent logic runs server-side and
streams typed events to any client (the terminal CLI, or a future web UI) over
Server-Sent Events, so both share one agent core.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.app.agent.events import event_parts
from backend.app.core.budget import BudgetViolation, enforce_agent_budget, enforce_anonymous_rate_limit
from backend.app.core.config import get_settings
from backend.app.core.request_context import request_id as current_request_id
from backend.app.models.schemas import AgentRequest

router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger(__name__)


def _stream_agent(*args, **kwargs):
    from backend.app.agent.runtime import stream_agent

    return stream_agent(*args, **kwargs)


def _run_agent(*args, **kwargs):
    from backend.app.agent.runtime import run_agent

    return run_agent(*args, **kwargs)


def _budget_violation(request: AgentRequest):
    settings = get_settings()
    return enforce_agent_budget(
        request,
        max_question_chars=settings.agent_max_question_chars,
        max_history_turns=settings.agent_max_history_turns,
    )


def _client_rate_key(request: Request) -> str:
    settings = get_settings()
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if settings.trust_proxy_headers and forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "anonymous"


def _rate_violation(http_request: Request) -> BudgetViolation | None:
    settings = get_settings()
    return enforce_anonymous_rate_limit(
        _client_rate_key(http_request),
        requests_per_minute=settings.anon_requests_per_minute,
    )


def _sse_error_frame(violation: BudgetViolation, request_id: str | None = None) -> str:
    frame = {
        "type": "error",
        "payload": violation.message,
        "meta": {"code": violation.code},
    }
    if request_id:
        frame["meta"]["request_id"] = request_id
    return f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"


@router.post("/stream")
def agent_stream(request: AgentRequest, http_request: Request) -> StreamingResponse:
    """Stream event frames for one question-answer turn as SSE.

    SSE contract:
    - Each event is encoded as a line frame:
      ``data: {"type": "...", "payload": ...}``
    - ``type`` is one of: ``plan``, ``text``, ``tool_call``,
      ``tool_result``, ``reflect``, ``final``, ``error``.
    - Errors in the loop are emitted as ``type=error`` and then terminated.
    - Stream termination is always signaled by a literal ``data: [DONE]`` frame.

    Request contract:
    - Body is ``AgentRequest`` with required ``question`` and optional ``history``.
    """
    violation = _budget_violation(request)
    if violation is None:
        violation = _rate_violation(http_request)
    if violation is not None:
        def budget_error():
            yield _sse_error_frame(violation, current_request_id())
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            budget_error(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    history = [{"role": t.role, "content": t.content} for t in request.history]
    settings = get_settings()
    production = settings.env.strip().lower() == "production"
    request_id = current_request_id()

    def events():
        try:
            for event in _stream_agent(
                request.question,
                history=history,
                session_id=request.session_id,
                retry=request.retry,
            ):
                kind, payload, meta = event_parts(event)
                frame = {"type": kind, "payload": payload}
                if meta:
                    frame["meta"] = meta
                yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            if production:
                logger.exception("agent stream failed", extra={"request_id": request_id})
                yield _sse_error_frame(
                    BudgetViolation("internal_error", "Internal Server Error"),
                    request_id,
                )
            else:
                yield f"data: {json.dumps({'type': 'error', 'payload': str(exc)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("")
def agent(request: AgentRequest, http_request: Request) -> dict:
    """Run the agent loop once and return the final structured result.

    This shares the same request schema as ``/api/agent/stream`` but returns one
    aggregate payload rather than incremental SSE frames.
    """
    violation = _budget_violation(request)
    if violation is None:
        violation = _rate_violation(http_request)
    if violation is not None:
        raise HTTPException(
            status_code=429 if violation.code == "rate_limited" else 400,
            detail={"code": violation.code, "message": violation.message},
        )

    history = [{"role": t.role, "content": t.content} for t in request.history]
    return _run_agent(request.question, history=history, session_id=request.session_id, retry=request.retry)
