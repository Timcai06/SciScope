"""Agentic loop: the LLM orchestrates SciScope tools to answer a question.

Architecture mirrors OpenCode / Claude Code (verified against their source, not
guessed):
  * stream -> act -> observe -> repeat (Claude Code's heartbeat)
  * the loop is a generator that yields typed events (text / tool_call /
    tool_result / final) — OpenCode's ``fullStream`` of typed parts, which the
    TUI consumes for live rendering.
  * tools are read-only, so a step's tool calls run in parallel (Claude Code's
    "partition by safety, run reads in parallel").
  * termination: the model emits no tool calls (natural completion) or the step
    cap is hit.

Unlike ``evidence_chat`` (fixed retrieve->answer pipeline), the model itself
chooses which tools to call and in how many steps.
"""

from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterator

from backend.app.agent.tools import TOOL_SCHEMAS, execute_tool

LLM_BASE = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
MAX_STEPS = 5

SYSTEM_PROMPT = (
    "你是 SciScope 科研文献智能体,可访问一个 16 万篇科技文献的知识库。"
    "你拥有以下工具:search_literature(检索论文)、get_trends(研究趋势)、"
    "recommend_papers(相似论文推荐,需 paper_id)、query_knowledge_graph(知识图谱/研究社区)。"
    "请根据用户问题自主选择并调用合适的工具(可多步:如先检索拿到 paper_id 再推荐);"
    "拿到工具结果后,用中文综合归纳作答,引用论文标题,只依据工具返回的真实数据,"
    "不要编造;若工具未返回有用信息,如实说明。"
    "注意:检索结果里的「摘要片段」是论文摘要节选,「作者」才是作者,不要把摘要当作者。"
)


def _detect_model() -> str | None:
    try:
        with urllib.request.urlopen(LLM_BASE.rstrip("/") + "/models", timeout=5) as resp:
            return json.loads(resp.read().decode())["data"][0]["id"]
    except Exception:
        return None


def _stream_chat(messages: list[dict], model: str, tools: list | None) -> Iterator[tuple[str, Any]]:
    """Stream a chat completion. Yields ('text', delta); returns (full_text, tool_calls).

    Accumulates streamed tool-call deltas (name + argument fragments) by index,
    the way the OpenAI streaming protocol delivers them.
    """
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True,
                            "temperature": 0.1, "max_tokens": 700}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        LLM_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    full_text = ""
    acc: dict[int, dict[str, Any]] = {}
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                full_text += delta["content"]
                yield ("text", delta["content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = acc.setdefault(idx, {"id": None, "name": None, "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    tool_calls = [
        {"id": s["id"] or s["name"], "type": "function",
         "function": {"name": s["name"], "arguments": s["arguments"]}}
        for s in (acc[i] for i in sorted(acc))
        if s["name"]
    ]
    return full_text, tool_calls


def _drain(gen: Iterator[tuple[str, Any]], forward) -> tuple[str, list[dict]]:
    """Forward 'text' events via `forward`, return the generator's (text, tool_calls)."""
    while True:
        try:
            kind, payload = next(gen)
        except StopIteration as stop:
            return stop.value
        forward(kind, payload)


def _compact(messages: list[dict], budget_chars: int = 20000) -> None:
    """Lightweight context 'snip' (à la Claude Code): if the running transcript
    grows past budget, truncate older tool results in place — keep structure and
    the most recent turns intact so we never overflow the 8k window.
    """
    total = sum(len(str(m.get("content") or "")) for m in messages)
    if total <= budget_chars:
        return
    for m in messages[1:-4]:  # keep system + last 4 messages full
        if m.get("role") == "tool" and len(str(m.get("content") or "")) > 400:
            m["content"] = str(m["content"])[:400] + " …(结果已压缩)"


def _run_tools(tool_calls: list[dict]) -> list[str]:
    """Execute a step's tool calls in parallel (all SciScope tools are read-only)."""
    def one(tc: dict) -> str:
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        return execute_tool(tc["function"]["name"], args)

    if len(tool_calls) == 1:
        return [one(tool_calls[0])]
    with ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as pool:
        return list(pool.map(one, tool_calls))


def stream_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
) -> Iterator[tuple[str, Any]]:
    """Event stream for the agentic loop. Yields:
    ('text', delta) | ('tool_call', {name,args}) | ('tool_result', {name,result})
    | ('final', answer).
    """
    model = model or _detect_model()
    if not model:
        yield ("final", "本地大模型未运行(:8001)。请先 `make llm`。")
        return

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})

    text_events: list[tuple[str, Any]] = []
    forward = lambda k, p: text_events.append((k, p))  # noqa: E731

    for _ in range(MAX_STEPS):
        _compact(messages)
        text_events.clear()
        full_text, tool_calls = _drain(_stream_chat(messages, model, TOOL_SCHEMAS), forward)
        for ev in text_events:
            yield ev
        if not tool_calls:
            yield ("final", full_text)
            return
        messages.append({"role": "assistant", "content": full_text, "tool_calls": tool_calls})
        for tc in tool_calls:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            yield ("tool_call", {"name": tc["function"]["name"], "args": args})
        results = _run_tools(tool_calls)
        for tc, result in zip(tool_calls, results):
            yield ("tool_result", {"name": tc["function"]["name"], "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", tc["function"]["name"]), "content": result})

    # Step cap reached — force a final synthesis without more tools.
    messages.append({"role": "user", "content": "请基于以上工具结果,用中文给出最终回答。"})
    text_events.clear()
    full_text, _ = _drain(_stream_chat(messages, model, None), forward)
    for ev in text_events:
        yield ev
    yield ("final", full_text)


def run_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> dict[str, Any]:
    """Non-streaming convenience wrapper (drains stream_agent)."""
    answer = ""
    tools_used: list[dict] = []
    steps = 0
    for kind, payload in stream_agent(question, history, model):
        if kind == "final":
            answer = payload
        elif kind == "tool_call":
            steps += 1
            tools_used.append({"name": payload["name"], "args": payload["args"]})
            if on_event:
                on_event("tool_call", payload)
        elif kind == "tool_result" and on_event:
            on_event("tool_result", payload)
    return {"answer": answer, "steps": steps, "tools_used": tools_used, "model": model or _detect_model()}
