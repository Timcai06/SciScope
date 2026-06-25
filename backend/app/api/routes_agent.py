"""Agentic assistant API — the SciScope agent loop over HTTP.

Mirrors OpenCode's server/client split: the agent logic runs server-side and
streams typed events to any client (the terminal CLI, or a future web UI) over
Server-Sent Events, so both share one agent core.
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.agent.loop import run_agent, stream_agent
from backend.app.models.schemas import AgentRequest

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/stream")
def agent_stream(request: AgentRequest) -> StreamingResponse:
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
    history = [{"role": t.role, "content": t.content} for t in request.history]

    def events():
        try:
            for kind, payload in stream_agent(request.question, history=history):
                yield f"data: {json.dumps({'type': kind, 'payload': payload}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'payload': str(exc)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("")
def agent(request: AgentRequest) -> dict:
    """Run the agent loop once and return the final structured result.

    This shares the same request schema as ``/api/agent/stream`` but returns one
    aggregate payload rather than incremental SSE frames.
    """
    history = [{"role": t.role, "content": t.content} for t in request.history]
    return run_agent(request.question, history=history)
