"""Typed event helpers shared by agent runtimes.

The HTTP API and TUI consume the same event stream regardless of whether the
turn is driven by the legacy ReAct loop or the LangGraph orchestration layer.
Keeping the event shape explicit makes runtime migration a contract-preserving
change instead of a UI-visible rewrite.
"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias


AgentEventType: TypeAlias = Literal["plan", "text", "tool_call", "tool_result", "reflect", "final"]
AgentEvent: TypeAlias = tuple[AgentEventType, Any]


def summarize_events(events: list[AgentEvent]) -> dict[str, Any]:
    """Build the aggregate ``/api/agent`` response from streamed events."""
    answer = ""
    tools_used: list[dict[str, Any]] = []
    steps = 0
    for kind, payload in events:
        if kind == "final":
            answer = str(payload)
        elif kind == "tool_call" and isinstance(payload, dict):
            steps += 1
            tools_used.append({"name": payload.get("name"), "args": payload.get("args") or {}})
    return {"answer": answer, "steps": steps, "tools_used": tools_used}
