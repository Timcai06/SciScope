"""LangGraph-backed orchestration runtime for the SciScope agent.

The legacy ReAct loop remains the behavior reference, but the control flow is
now expressed as a StateGraph:

``prepare -> plan -> llm_step -> execute_tools -> llm_step -> reflect/final``.

This gives the product a standard agent orchestration layer while preserving the
existing SSE contract consumed by the TUI and future web clients.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Callable, Iterator, Literal, TypedDict

from backend.app.agent import loop as legacy_loop
from backend.app.agent.events import AgentEvent, summarize_events
from backend.app.agent.tools import TOOL_SCHEMAS


GraphRoute = Literal["plan", "llm_step", "execute_tools", "reflect", "force_synthesis", "end"]


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict]
    model: str | None
    messages: list[dict]
    tool_calls: list[dict]
    executed: dict[str, str]
    tools_total: int
    retries: int
    step: int
    last_answer: str
    runtime: str
    route: GraphRoute
    emit: list[AgentEvent]


def _load_langgraph():
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:  # pragma: no cover - exercised through runtime error path
        raise RuntimeError(
            "LangGraph runtime requested but langgraph is not installed. "
            "Run `make install-backend` or `python -m pip install langgraph`."
        ) from exc
    return StateGraph, END


def _prepare(state: AgentState) -> AgentState:
    model = state.get("model") or legacy_loop._detect_model()
    if not model:
        return {
            "runtime": "langgraph",
            "route": "end",
            "emit": [("final", "本地大模型未运行(:8001)。请先 `make llm`。")],
        }
    messages = [{"role": "system", "content": legacy_loop.SYSTEM_PROMPT}]
    messages.extend(state.get("history") or [])
    messages.append({"role": "user", "content": state["question"]})
    return {
        "model": model,
        "messages": messages,
        "executed": {},
        "tools_total": 0,
        "retries": 0,
        "step": 0,
        "runtime": "langgraph",
        "route": "plan",
        "emit": [],
    }


def _plan(state: AgentState) -> AgentState:
    question = state["question"]
    model = state["model"]
    messages = list(state.get("messages") or [])
    if not model or not legacy_loop._needs_plan(question):
        return {"messages": messages, "route": "llm_step", "emit": []}

    plan = legacy_loop._make_plan(question, model)
    if not plan:
        return {"messages": messages, "route": "llm_step", "emit": []}

    messages.append(
        {
            "role": "assistant",
            "content": "执行计划:\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(plan, 1)),
        }
    )
    messages.append({"role": "user", "content": "请按上述计划逐步调用工具完成,最后用中文综合作答。"})
    return {"messages": messages, "route": "llm_step", "emit": [("plan", plan)]}


def _llm_step(state: AgentState) -> AgentState:
    messages = list(state.get("messages") or [])
    legacy_loop._compact(messages)
    text_events: list[AgentEvent] = []
    full_text, tool_calls = legacy_loop._drain(
        legacy_loop._stream_chat(messages, state["model"], TOOL_SCHEMAS),
        lambda kind, payload: text_events.append((kind, payload)),
    )
    next_state: AgentState = {
        "messages": messages,
        "last_answer": full_text,
        "tool_calls": tool_calls,
        "step": int(state.get("step") or 0) + 1,
        "emit": text_events,
    }
    if tool_calls:
        messages.append({"role": "assistant", "content": full_text, "tool_calls": tool_calls})
        next_state["messages"] = messages
        next_state["tools_total"] = int(state.get("tools_total") or 0) + len(tool_calls)
        next_state["route"] = "execute_tools"
    else:
        next_state["tools_total"] = int(state.get("tools_total") or 0)
        next_state["route"] = "reflect"
    return next_state


def _tool_call_event(tool_call: dict) -> AgentEvent:
    try:
        args = json.loads(tool_call["function"].get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {}
    return ("tool_call", {"name": tool_call["function"]["name"], "args": args})


def _execute_tools(state: AgentState) -> AgentState:
    messages = list(state.get("messages") or [])
    tool_calls = list(state.get("tool_calls") or [])
    executed = dict(state.get("executed") or {})
    emit: list[AgentEvent] = [_tool_call_event(tool_call) for tool_call in tool_calls]
    results = legacy_loop._run_tools(tool_calls, executed) if tool_calls else []
    for tool_call, result in zip(tool_calls, results):
        name = tool_call["function"]["name"]
        emit.append(("tool_result", {"name": name, "result": result}))
        messages.append({"role": "tool", "tool_call_id": tool_call.get("id", name), "content": result})

    route: GraphRoute = "force_synthesis" if int(state.get("step") or 0) >= legacy_loop.MAX_STEPS else "llm_step"
    return {"messages": messages, "executed": executed, "tool_calls": [], "route": route, "emit": emit}


def _reflect(state: AgentState) -> AgentState:
    retries = int(state.get("retries") or 0)
    answer = state.get("last_answer") or ""
    reason = None
    if retries < legacy_loop.MAX_RETRIES:
        reason = legacy_loop._reflect_reason(answer, int(state.get("tools_total") or 0), state["question"])
        if reason is None and int(state.get("tools_total") or 0) > 0:
            reason = legacy_loop._self_critique(state["question"], answer, state["model"])

    if not reason:
        return {"route": "end", "emit": [("final", answer)]}

    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": answer})
    messages.append(
        {
            "role": "user",
            "content": (
                reason + " 请直接据此重新检索并给出改进后的【完整中文回答】,"
                "不要回复「好的」、不要复述计划或描述你将要做什么。"
            ),
        }
    )
    return {
        "messages": messages,
        "retries": retries + 1,
        "route": "llm_step",
        "emit": [("reflect", reason)],
    }


def _force_synthesis(state: AgentState) -> AgentState:
    messages = list(state.get("messages") or [])
    messages.append({"role": "user", "content": "请基于以上工具结果,用中文给出最终回答。"})
    text_events: list[AgentEvent] = []
    full_text, _ = legacy_loop._drain(
        legacy_loop._stream_chat(messages, state["model"], None),
        lambda kind, payload: text_events.append((kind, payload)),
    )
    return {"messages": messages, "last_answer": full_text, "route": "end", "emit": [*text_events, ("final", full_text)]}


def _route(state: AgentState) -> GraphRoute:
    return state.get("route") or "end"


@lru_cache(maxsize=1)
def _build_graph():
    StateGraph, END = _load_langgraph()
    graph = StateGraph(AgentState)
    graph.add_node("prepare", _prepare)
    graph.add_node("plan", _plan)
    graph.add_node("llm_step", _llm_step)
    graph.add_node("execute_tools", _execute_tools)
    graph.add_node("reflect", _reflect)
    graph.add_node("force_synthesis", _force_synthesis)
    graph.set_entry_point("prepare")
    graph.add_conditional_edges("prepare", _route, {"plan": "plan", "end": END})
    graph.add_edge("plan", "llm_step")
    graph.add_conditional_edges(
        "llm_step",
        _route,
        {"execute_tools": "execute_tools", "reflect": "reflect", "end": END},
    )
    graph.add_conditional_edges(
        "execute_tools",
        _route,
        {"llm_step": "llm_step", "force_synthesis": "force_synthesis", "end": END},
    )
    graph.add_conditional_edges("reflect", _route, {"llm_step": "llm_step", "end": END})
    graph.add_edge("force_synthesis", END)
    return graph.compile(name="sciscope-agent")


def _events_from_update(update: dict[str, Any]) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    for payload in update.values():
        if isinstance(payload, dict):
            events.extend(payload.get("emit") or [])
    return events


def stream_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
) -> Iterator[AgentEvent]:
    """Run one agent turn through the LangGraph StateGraph and stream node events."""
    inputs = {"question": question, "history": history or [], "model": model}
    for update in _build_graph().stream(inputs, stream_mode="updates"):
        if isinstance(update, dict):
            yield from _events_from_update(update)


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
