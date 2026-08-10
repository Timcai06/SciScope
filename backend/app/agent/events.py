"""Typed event helpers for the agent runtime.

The HTTP API and TUI consume the same event stream emitted by the LangGraph
orchestration layer. Keeping the event shape explicit makes orchestration
changes contract-preserving instead of a UI-visible rewrite.
"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias


AgentEventType: TypeAlias = Literal[
    "intent", "plan", "text", "tool_call", "tool_progress", "tool_result", "reflect", "final"
]
AgentEventMeta: TypeAlias = dict[str, Any]
AgentEvent: TypeAlias = tuple[AgentEventType, Any] | tuple[AgentEventType, Any, AgentEventMeta]


def event_parts(event: AgentEvent) -> tuple[AgentEventType, Any, AgentEventMeta]:
    """Normalize 2-tuple and 3-tuple agent events."""
    if len(event) == 3:
        kind, payload, meta = event
        return kind, payload, meta
    kind, payload = event
    return kind, payload, {}


def summarize_events(events: list[AgentEvent]) -> dict[str, Any]:
    """Build the aggregate ``/api/agent`` response from streamed events."""
    answer = ""
    tools_used: list[dict[str, Any]] = []
    steps = 0
    structured_answer: dict[str, Any] | None = None
    for event in events:
        kind, payload, meta = event_parts(event)
        if kind == "final":
            answer = str(payload)
            if isinstance(meta.get("structured_answer"), dict):
                structured_answer = meta["structured_answer"]
        elif kind == "tool_call" and isinstance(payload, dict):
            steps += 1
            tools_used.append({"name": payload.get("name"), "args": payload.get("args") or {}})
    response = {"answer": answer, "steps": steps, "tools_used": tools_used}
    if structured_answer is not None:
        response["structured_answer"] = structured_answer
    return response
