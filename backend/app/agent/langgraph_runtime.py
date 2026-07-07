"""LangGraph-backed orchestration runtime for the SciScope agent.

The agent control flow is expressed as a single StateGraph:

``prepare -> plan -> llm_step -> execute_tools -> llm_step -> reflect/final``.

This gives the product a standard agent orchestration layer while preserving the
existing SSE contract consumed by the TUI and future web clients.
"""

from __future__ import annotations

import json
import re
import time
from uuid import uuid4
from functools import lru_cache
from typing import Any, Callable, Iterator, Literal, TypedDict

from backend.app.agent.compaction import autocompact
from backend.app.agent.compaction import estimate_tokens as _estimate_tokens
from backend.app.agent.compaction import messages_tokens as _messages_tokens
from backend.app.agent.events import AgentEvent, summarize_events
from backend.app.agent.llm import build_system_prompt, compact, complete, detect_model, drain, stream_chat
from backend.app.agent import session_memory
from backend.app.agent.planning import make_plan, needs_plan
from backend.app.agent.reflection import reflect_reason, self_critique
from backend.app.agent.tool_runner import repair_missing_tool_results, run_tools
from backend.app.agent.tools import TOOL_SCHEMAS
from backend.app.core.config import get_settings

MAX_STEPS = 6
MAX_RETRIES = 1

# Transition narration the model keeps prepending to final answers despite the
# prompt ban ("好的，数据已全部返回。下面综合作答。---"). Stripped deterministically:
# a short leading line containing one of these phrases, plus a following --- rule.
_NARRATION_MARKERS = ("综合作答", "数据已全部返回", "证据已足够", "证据充分了", "现在综合")
_HR_RE = re.compile(r"^\s*-{3,}\s*\n+")


def _strip_narration(text: str) -> str:
    out = (text or "").lstrip()
    first, sep, rest = out.partition("\n")
    if sep and len(first) <= 60 and any(marker in first for marker in _NARRATION_MARKERS):
        out = _HR_RE.sub("", rest.lstrip("\n"))
    return out


GraphRoute = Literal["plan", "llm_step", "execute_tools", "reflect", "force_synthesis", "end"]

NODE_PHASES = {
    "prepare": "理解问题",
    "plan": "制定研究计划",
    "llm_step": "推理与检索决策",
    "execute_tools": "证据检索",
    "reflect": "自检修正",
    "force_synthesis": "综合回答",
}


def _skill_tool_budget(question: str) -> int | None:
    """Hard cap tool loops for explicit SciScope skill prompts."""
    if "你正在执行 SciScope 技能" not in question:
        return None
    return 2


def _tool_call_budget(question: str) -> int:
    skill_budget = _skill_tool_budget(question)
    configured_budget = get_settings().agent_max_tool_calls
    if skill_budget is None:
        return configured_budget
    return min(configured_budget, skill_budget)


def _skill_input(question: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}:\s*\n(?P<input>.*?)(?:\n\n工作要求:|\Z)", question, flags=re.S)
    if not match:
        return ""
    return match.group("input").strip()


def _forced_skill_tool_call(question: str) -> dict[str, Any] | None:
    """Deterministically recover when a skill prompt skips its required first tool."""
    if "SciScope 技能: 论断核查" in question:
        claim = _skill_input(question, "输入论断")
        if claim:
            return {
                "id": "forced_" + uuid4().hex,
                "type": "function",
                "function": {"name": "verify_claim", "arguments": json.dumps({"claim": claim}, ensure_ascii=False)},
            }
    if "SciScope 技能: 趋势分析" in question:
        keyword = _skill_input(question, "研究主题")
        if keyword:
            return {
                "id": "forced_" + uuid4().hex,
                "type": "function",
                "function": {"name": "get_trends", "arguments": json.dumps({"keyword": keyword}, ensure_ascii=False)},
            }
    if "SciScope 技能: 论文推荐" in question:
        query = _skill_input(question, "用户需求")
        if query:
            return {
                "id": "forced_" + uuid4().hex,
                "type": "function",
                "function": {"name": "search_literature", "arguments": json.dumps({"query": query}, ensure_ascii=False)},
            }
    if "SciScope 技能: 文献综述" in question:
        topic = _skill_input(question, "研究主题")
        if topic:
            return {
                "id": "forced_" + uuid4().hex,
                "type": "function",
                "function": {"name": "summarize_field", "arguments": json.dumps({"topic": topic}, ensure_ascii=False)},
            }
    return None


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
    tokens_in: int
    tokens_out: int
    stop_reason: str


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


def _final_extra(state: AgentState, stop_reason: str, add_in: int = 0, add_out: int = 0) -> dict[str, Any]:
    """Build the final-event meta extras: why the turn stopped + token usage."""
    return {
        "stop_reason": stop_reason,
        "tokens_in": int(state.get("tokens_in") or 0) + add_in,
        "tokens_out": int(state.get("tokens_out") or 0) + add_out,
    }


def _finish_node(node: str, started_at: float, state: AgentState, updates: AgentState, extra: dict[str, Any] | None = None) -> AgentState:
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
    if extra:
        meta.update(extra)
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
            "emit": [("final", "本地大模型未运行(:8001)。请先 `make llm`,或设置 DEEPSEEK_API_KEY 使用云端模型。")],
        }, extra={"stop_reason": "no_model", "tokens_in": 0, "tokens_out": 0})
    messages = [{"role": "system", "content": build_system_prompt()}]
    # Session memory (Claude Code SessionMemory): recall prior research focus, then
    # record this question for future turns. No-ops without a session id.
    session_id = state.get("session_id")
    recalled = session_memory.recall_prompt(session_id)
    if recalled:
        messages.append({"role": "system", "content": recalled})
    session_memory.remember(session_id, "研究关注: " + (state["question"] or "")[:80])
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
        "tokens_in": 0,
        "tokens_out": 0,
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

    # Feed the planner the previous answer so follow-up references (「第 2 篇论文」)
    # resolve to real titles instead of a fabricated paper_id.
    history = state.get("history") or []
    last_answer = next((m.get("content") for m in reversed(history) if m.get("role") == "assistant"), "")
    plan = make_plan(question, model, context=str(last_answer or "")[:600])
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


AUTOCOMPACT_BUDGET = 6000  # tokens; above this, summarize older turns (Claude Code autoCompact)


def _summarize_transcript(transcript: str, model: str) -> str:
    """LLM summarizer injected into autocompact — condenses older turns.

    Structured like Claude Code's compact prompt (scaled down): the summary must
    preserve exactly what later turns need to keep working — the user's goal and
    corrections, retrieved evidence with paper_ids (still valid tool arguments
    after compaction), settled conclusions, and unfinished work.
    """
    messages = [
        {"role": "system", "content": (
            "你是对话压缩器,只输出摘要文本,不要评论或展开。"
            "把这段科研对话压缩成供后续轮次继续工作的备忘,按以下四项输出,每项一行,没有则写「无」:\n"
            "1. 用户目标: 用户想解决什么,以及中途给过的指示或纠正;\n"
            "2. 已检索证据: 关键论文的标题、年份、paper_id 与要点(paper_id 必须原样保留,后续轮次要用它调用工具);\n"
            "3. 已得结论: 已经明确回答过的内容;\n"
            "4. 未完成: 还没做完的检索或还没答复的问题。"
        )},
        {"role": "user", "content": transcript},
    ]
    return complete(messages, model)


def _maybe_autocompact(messages: list[dict], model: str | None) -> dict[str, Any] | None:
    """When the running context is still over budget, summarize older turns.

    Returns compaction telemetry (for the node meta) or None when nothing fired.
    """
    if not model or _messages_tokens(messages) <= AUTOCOMPACT_BUDGET:
        return None
    result = autocompact(messages, lambda t: _summarize_transcript(t, model), token_budget=AUTOCOMPACT_BUDGET)
    if result.strategy == "none":
        return None
    return {"compaction": {
        "strategy": result.strategy,
        "tokens_freed": result.tokens_freed,
        "messages_summarized": result.messages_summarized,
    }}


def _llm_step(state: AgentState) -> AgentState:
    started_at = time.perf_counter()
    messages = list(state.get("messages") or [])
    compact(messages)  # cheap microcompact first
    compaction_meta = _maybe_autocompact(messages, state.get("model"))  # LLM summary if still over budget
    repair_missing_tool_results(messages)  # never send an unanswered tool_call to the API
    tokens_in = int(state.get("tokens_in") or 0) + _messages_tokens(messages)
    text_events: list[AgentEvent] = []
    full_text, tool_calls = drain(
        stream_chat(messages, state["model"], TOOL_SCHEMAS),
        lambda kind, payload: text_events.append((kind, payload)),
    )
    if not tool_calls and int(state.get("tools_total") or 0) == 0:
        forced_call = _forced_skill_tool_call(state["question"])
        if forced_call:
            tool_calls = [forced_call]
    budget = _tool_call_budget(state["question"])
    if tool_calls:
        remaining = max(budget - int(state.get("tools_total") or 0), 0)
        tool_calls = tool_calls[:remaining]
    next_state: AgentState = {
        "messages": messages,
        "last_answer": full_text,
        "tool_calls": tool_calls,
        "step": int(state.get("step") or 0) + 1,
        "tokens_in": tokens_in,
        "tokens_out": int(state.get("tokens_out") or 0) + _estimate_tokens(full_text),
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
    return _finish_node("llm_step", started_at, state, next_state, extra=compaction_meta)


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
    call_events: list[AgentEvent] = [_tool_call_event(tool_call) for tool_call in tool_calls]
    # Streaming tools yield progress strings while they run; collect them for a
    # finer tool timeline. (LangGraph's "updates" stream surfaces a node's events
    # only after it returns, so these batch with the node — the contract is
    # plumbed end to end; real-time surfacing would need event-level streaming.)
    progress_events: list[AgentEvent] = []
    on_progress = lambda name, message: progress_events.append(
        ("tool_progress", {"name": name, "message": message})
    )
    results = run_tools(tool_calls, executed, on_progress=on_progress) if tool_calls else []
    result_events: list[AgentEvent] = []
    for tool_call, result in zip(tool_calls, results):
        name = tool_call["function"]["name"]
        result_events.append(("tool_result", {"name": name, "result": result}))
        messages.append({"role": "tool", "tool_call_id": tool_call.get("id", name), "content": result})
    emit: list[AgentEvent] = [*call_events, *progress_events, *result_events]

    budget = _tool_call_budget(state["question"])
    tools_total = int(state.get("tools_total") or 0)
    if tools_total >= budget:
        route: GraphRoute = "force_synthesis"
        stop_reason = "tool_budget"
    else:
        route = "force_synthesis" if int(state.get("step") or 0) >= MAX_STEPS else "llm_step"
        stop_reason = "max_steps" if route == "force_synthesis" else ""
    return _finish_node(
        "execute_tools",
        started_at,
        state,
        {"messages": messages, "executed": executed, "tool_calls": [], "route": route, "stop_reason": stop_reason, "emit": emit},
    )


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
        return _finish_node(
            "reflect", started_at, state,
            {"route": "end", "emit": [("final", _strip_narration(answer))]},
            extra=_final_extra(state, "completed"),
        )

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
    repair_missing_tool_results(messages)  # repair before adding the synthesis turn
    messages.append({
        "role": "user",
        "content": (
            "请基于以上工具结果,用中文给出最终回答:结论先行,"
            "关键论断标注出处(论文标题+年份);证据不足处如实说明,不要硬撑;"
            "控制在 500 字内,结尾不要加总结段。"
        ),
    })
    call_in = _messages_tokens(messages)
    text_events: list[AgentEvent] = []
    full_text, _ = drain(
        stream_chat(messages, state["model"], None),
        lambda kind, payload: text_events.append((kind, payload)),
    )
    return _finish_node(
        "force_synthesis", started_at, state,
        {"messages": messages, "last_answer": full_text, "route": "end", "emit": [*text_events, ("final", _strip_narration(full_text))]},
        extra=_final_extra(state, state.get("stop_reason") or "max_steps", call_in, _estimate_tokens(full_text)),
    )


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


def _stream_command(question: str, session_id: str | None) -> Iterator[AgentEvent]:
    """Handle a slash command outside the LLM loop (Claude Code command interception)."""
    from backend.app.agent.commands import parse_command, run_command

    started_at = time.perf_counter()
    name = (parse_command(question) or ("help", ""))[0]
    output = run_command(question) or ""
    meta: dict[str, Any] = {
        "runtime": "command",
        "node": "command",
        "phase": f"/{name}",
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        "stop_reason": "command",
        "tokens_in": 0,
        "tokens_out": 0,
    }
    if session_id:
        meta["session_id"] = session_id
    yield ("plan", [f"执行命令 /{name}"], meta)
    yield ("final", output, meta)


def stream_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    session_id: str | None = None,
    retry: bool = False,
) -> Iterator[AgentEvent]:
    """Run one agent turn and stream node events.

    A leading-slash message is intercepted as a slash command and answered without
    invoking the LLM loop; everything else runs through the LangGraph StateGraph.
    """
    from backend.app.agent.commands import command_kind, is_command, parse_command, run_command

    if is_command(question):
        _, arg = parse_command(question) or ("", "")
        # Prompt commands (/review, /trend, …) expand a skill template and run
        # through the loop like any question; answer commands (/help, /search,
        # or a prompt command with no argument) reply directly.
        if command_kind(question) == "prompt" and arg.strip():
            question = run_command(question) or question
        else:
            yield from _stream_command(question, session_id)
            return
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
    # Carry stop_reason + token usage (and runtime, e.g. the command path) from the
    # final event's meta to the aggregate.
    for event in events:
        kind, _payload, *rest = event
        meta = rest[0] if rest else {}
        if kind == "final" and isinstance(meta, dict):
            for key in ("stop_reason", "tokens_in", "tokens_out", "runtime"):
                if key in meta:
                    response[key] = meta[key]
    return response
