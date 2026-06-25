"""Runtime selector for SciScope's research agent.

``langgraph`` is the product default. The legacy ReAct loop remains available as
an explicit compatibility fallback via ``SCISCOPE_AGENT_RUNTIME=legacy`` while
the codebase finishes migrating reusable primitives into the graph runtime.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Iterator

from backend.app.agent import loop as legacy_loop
from backend.app.agent.events import AgentEvent

_LEGACY_ALIASES = {"legacy", "loop", "react"}
_LANGGRAPH_ALIASES = {"langgraph", "graph", "stategraph"}


def selected_runtime_name() -> str:
    """Return the normalized agent runtime selected by environment."""
    raw = os.getenv("SCISCOPE_AGENT_RUNTIME", "langgraph").strip().lower()
    if raw in _LEGACY_ALIASES:
        return "legacy"
    if raw in _LANGGRAPH_ALIASES:
        return "langgraph"
    allowed = ", ".join(sorted(_LEGACY_ALIASES | _LANGGRAPH_ALIASES))
    raise ValueError(f"Unsupported SCISCOPE_AGENT_RUNTIME={raw!r}. Expected one of: {allowed}")


def _langgraph_runtime():
    from backend.app.agent import langgraph_runtime

    return langgraph_runtime


def stream_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    session_id: str | None = None,
) -> Iterator[AgentEvent]:
    """Stream an agent turn from the selected runtime."""
    runtime = selected_runtime_name()
    if runtime == "langgraph":
        yield from _langgraph_runtime().stream_agent(question, history=history, model=model, session_id=session_id)
        return
    yield from legacy_loop.stream_agent(question, history=history, model=model)


def run_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Run one agent turn and return the selected runtime's aggregate response."""
    runtime = selected_runtime_name()
    if runtime == "langgraph":
        return _langgraph_runtime().run_agent(question, history=history, model=model, on_event=on_event, session_id=session_id)
    return legacy_loop.run_agent(question, history=history, model=model, on_event=on_event)
