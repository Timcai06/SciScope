"""LangGraph-backed orchestration runtime for the SciScope agent.

Phase one keeps behavior equivalent by wrapping the proven legacy ReAct loop in
a small StateGraph. That gives the project a mainstream orchestration boundary
now, while leaving room to split planning, tool execution, reflection, and final
synthesis into first-class graph nodes without changing API or TUI contracts.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, TypedDict

from backend.app.agent import loop as legacy_loop
from backend.app.agent.events import AgentEvent, summarize_events


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict]
    model: str | None
    events: list[AgentEvent]
    runtime: str


def _load_langgraph():
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:  # pragma: no cover - exercised via runtime tests
        raise RuntimeError(
            "LangGraph runtime requested but langgraph is not installed. "
            "Run `make install-backend` or `python -m pip install langgraph`."
        ) from exc
    return StateGraph, END


def _prepare(state: AgentState) -> AgentState:
    return {
        "question": state["question"],
        "history": state.get("history") or [],
        "model": state.get("model"),
        "runtime": "langgraph",
    }


def _run_legacy_agent(state: AgentState) -> AgentState:
    events = list(
        legacy_loop.stream_agent(
            state["question"],
            history=state.get("history") or [],
            model=state.get("model"),
        )
    )
    return {"events": events}


def _finalize(state: AgentState) -> AgentState:
    events = state.get("events") or []
    if not any(kind == "final" for kind, _ in events):
        events = [*events, ("final", "智能体运行结束,但未生成最终回答。")]
    return {"events": events, "runtime": "langgraph"}


def _build_graph():
    StateGraph, END = _load_langgraph()
    graph = StateGraph(AgentState)
    graph.add_node("prepare", _prepare)
    graph.add_node("agent_loop", _run_legacy_agent)
    graph.add_node("finalize", _finalize)
    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "agent_loop")
    graph.add_edge("agent_loop", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(name="sciscope-agent")


def stream_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
) -> Iterator[AgentEvent]:
    """Run one agent turn through the LangGraph StateGraph and replay events."""
    state = _build_graph().invoke({"question": question, "history": history or [], "model": model})
    yield from state.get("events") or []


def run_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> dict[str, Any]:
    """Aggregate the LangGraph event stream into the existing response shape."""
    events = list(stream_agent(question, history=history, model=model))
    for kind, payload in events:
        if kind in {"tool_call", "tool_result"} and on_event and isinstance(payload, dict):
            on_event(kind, payload)
    response = summarize_events(events)
    response["model"] = model or legacy_loop._detect_model()
    response["runtime"] = "langgraph"
    return response
