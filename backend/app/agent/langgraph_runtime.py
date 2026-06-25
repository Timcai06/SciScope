"""LangGraph-backed orchestration runtime for the SciScope agent.

The legacy ReAct loop remains the behavior reference, but the control flow is
now expressed as a StateGraph:

``prepare -> plan -> llm_step -> execute_tools -> llm_step -> reflect/final``.

This gives the product a standard agent orchestration layer while preserving the
existing SSE contract consumed by the TUI and future web clients.
"""

from __future__ import annotations

import json
import time
from uuid import uuid4
from functools import lru_cache
from typing import Any, Callable, Iterator, Literal, TypedDict

from backend.app.agent.events import AgentEvent, summarize_events
from backend.app.agent.llm import SYSTEM_PROMPT, compact, detect_model, drain, stream_chat
from backend.app.agent.planning import make_plan, needs_plan
from backend.app.agent.reflection import reflect_reason, self_critique
from backend.app.agent.tool_runner import run_tools
from backend.app.agent.tools import TOOL_SCHEMAS

MAX_STEPS = 6
MAX_RETRIES = 1


GraphRoute = Literal["plan", "llm_step", "execute_tools", "reflect", "force_synthesis", "end"]

NODE_PHASES = {
    "prepare": "理解问题",
    "plan": "制定研究计划",
    "llm_step": "推理与检索决策",
    "execute_tools": "证据检索",
    "reflect": "自检修正",
    "force_synthesis": "综合回答",
}


class AgentState(TypedDict, total=False):
    question: str
    session_id: str | None
    retry: bool
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
    node_meta: dict[str, Any]


def _load_langgraph():
    try:
        from langgraph.graph import END, StateGraph
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError as exc:  # pragma: no cover - exercised through runtime error path
        raise RuntimeError(
            "LangGraph runtime requested but langgraph is not installed. "
            "Run `make install-backend` or `python -m pip install langgraph`."
        ) from exc
    return StateGraph, END, MemorySaver


def _finish_node(node: str, started_at: float, state: AgentState, updates: AgentState) -> AgentState:
    meta = {
        "runtime": "langgraph",
        "node": node,
        "phase": NODE_PHASES.get(node, node),
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
    }
    session_id = state.get("session_id")
    if session_id:
        meta["session_id"] = session_id
    if state.get("retry"):
        meta["retry"] = True
    updates["node_meta"] = meta
    if updates.get("emit"):
        updates["emit"] = [(kind, payload, meta) for kind, payload, *_ in updates["emit"]]
    return updates


def _prepare(state: AgentState) -> AgentState:
    started_at = time.perf_counter()
    model = state.get("model") or detect_model()
    if not model:
        return _finish_node("prepare", started_at, state, {
            "runtime": "langgraph",
            "route": "end",
            "emit": [("final", "本地大模型未运行(:8001)。请先 `make llm`。")],
        })
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(state.get("history") or [])
    messages.append({"role": "user", "content": state["question"]})
    if state.get("retry"):
        messages.append({
            "role": "user",
            "content": (
                "这是同一会话线程上的 /retry 请求。请假设用户已经处理了上一轮错误或环境问题,"
                "不要复述错误,重新规划并调用必要工具;如果仍缺少依赖,给出明确恢复动作。"
            ),
        })
    return _finish_node("prepare", started_at, state, {
        "model": model,
        "messages": messages,
        "executed": {},
        "tools_total": 0,
        "retries": 0,
        "step": 0,
        "runtime": "langgraph",
        "route": "plan",
        "emit": [],
    })


def _plan(state: AgentState) -> AgentState:
    started_at = time.perf_counter()
    question = state["question"]
    model = state["model"]
    messages = list(state.get("messages") or [])
    if not model or not needs_plan(question):
        return _finish_node("plan", started_at, state, {"messages": messages, "route": "llm_step", "emit": []})

    plan = make_plan(question, model)
    if not plan:
        return _finish_node("plan", started_at, state, {"messages": messages, "route": "llm_step", "emit": []})

    messages.append(
        {
            "role": "assistant",
            "content": "执行计划:\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(plan, 1)),
        }
    )
    messages.append({"role": "user", "content": "请按上述计划逐步调用工具完成,最后用中文综合作答。"})
    return _finish_node("plan", started_at, state, {"messages": messages, "route": "llm_step", "emit": [("plan", plan)]})


def _llm_step(state: AgentState) -> AgentState:
    started_at = time.perf_counter()
    messages = list(state.get("messages") or [])
    compact(messages)
    text_events: list[AgentEvent] = []
    full_text, tool_calls = drain(
        stream_chat(messages, state["model"], TOOL_SCHEMAS),
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
    return _finish_node("llm_step", started_at, state, next_state)


def _tool_call_event(tool_call: dict) -> AgentEvent:
    try:
        args = json.loads(tool_call["function"].get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {}
    return ("tool_call", {"name": tool_call["function"]["name"], "args": args})


def _execute_tools(state: AgentState) -> AgentState:
    started_at = time.perf_counter()
    messages = list(state.get("messages") or [])
    tool_calls = list(state.get("tool_calls") or [])
    executed = dict(state.get("executed") or {})
    emit: list[AgentEvent] = [_tool_call_event(tool_call) for tool_call in tool_calls]
    results = run_tools(tool_calls, executed) if tool_calls else []
    for tool_call, result in zip(tool_calls, results):
        name = tool_call["function"]["name"]
        emit.append(("tool_result", {"name": name, "result": result}))
        messages.append({"role": "tool", "tool_call_id": tool_call.get("id", name), "content": result})

    route: GraphRoute = "force_synthesis" if int(state.get("step") or 0) >= MAX_STEPS else "llm_step"
    return _finish_node("execute_tools", started_at, state, {"messages": messages, "executed": executed, "tool_calls": [], "route": route, "emit": emit})


def _reflect(state: AgentState) -> AgentState:
    started_at = time.perf_counter()
    retries = int(state.get("retries") or 0)
    answer = state.get("last_answer") or ""
    reason = None
    if retries < MAX_RETRIES:
        reason = reflect_reason(answer, int(state.get("tools_total") or 0), state["question"])
        if reason is None and int(state.get("tools_total") or 0) > 0:
            reason = self_critique(state["question"], answer, state["model"])

    if not reason:
        return _finish_node("reflect", started_at, state, {"route": "end", "emit": [("final", answer)]})

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
    return _finish_node("reflect", started_at, state, {
        "messages": messages,
        "retries": retries + 1,
        "route": "llm_step",
        "emit": [("reflect", reason)],
    })


def _force_synthesis(state: AgentState) -> AgentState:
    started_at = time.perf_counter()
    messages = list(state.get("messages") or [])
    messages.append({"role": "user", "content": "请基于以上工具结果,用中文给出最终回答。"})
    text_events: list[AgentEvent] = []
    full_text, _ = drain(
        stream_chat(messages, state["model"], None),
        lambda kind, payload: text_events.append((kind, payload)),
    )
    return _finish_node("force_synthesis", started_at, state, {"messages": messages, "last_answer": full_text, "route": "end", "emit": [*text_events, ("final", full_text)]})


def _route(state: AgentState) -> GraphRoute:
    return state.get("route") or "end"


@lru_cache(maxsize=1)
def _build_graph():
    StateGraph, END, MemorySaver = _load_langgraph()
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
    return graph.compile(checkpointer=MemorySaver(), name="sciscope-agent")


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
    session_id: str | None = None,
    retry: bool = False,
) -> Iterator[AgentEvent]:
    """Run one agent turn through the LangGraph StateGraph and stream node events."""
    thread_id = session_id or f"sciscope-turn-{uuid4().hex}"
    inputs = {"question": question, "history": history or [], "model": model, "session_id": session_id, "retry": retry}
    config = {"configurable": {"thread_id": thread_id}}
    for update in _build_graph().stream(inputs, config=config, stream_mode="updates"):
        if isinstance(update, dict):
            yield from _events_from_update(update)


def run_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
    session_id: str | None = None,
    retry: bool = False,
) -> dict[str, Any]:
    """Aggregate the LangGraph event stream into the existing response shape."""
    events = list(stream_agent(question, history=history, model=model, session_id=session_id, retry=retry))
    for event in events:
        kind, payload, *_ = event
        if kind in {"tool_call", "tool_result"} and on_event and isinstance(payload, dict):
            on_event(kind, payload)
    response = summarize_events(events)
    response["model"] = model or detect_model()
    response["runtime"] = "langgraph"
    if session_id:
        response["session_id"] = session_id
    response["retry"] = retry
    return response
