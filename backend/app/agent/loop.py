"""Agentic loop: the LLM orchestrates SciScope tools to answer a question.

Unlike the fixed RAG pipeline in ``evidence_chat``, here the model itself decides
which tools to call (search / trends / recommend / graph), in how many steps, and
then writes a grounded final answer. This is the "research agent" core for the
terminal assistant.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

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
)


def _detect_model() -> str | None:
    try:
        with urllib.request.urlopen(LLM_BASE.rstrip("/") + "/models", timeout=5) as resp:
            return json.loads(resp.read().decode())["data"][0]["id"]
    except Exception:
        return None


def _chat(messages: list[dict], model: str, tools: list | None) -> dict:
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.1, "max_tokens": 700}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        LLM_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def run_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> dict[str, Any]:
    """Run the tool-using loop. Returns {answer, steps, model, messages}.

    ``on_event(kind, payload)`` is called for UI feedback: kind in
    {"tool_call", "tool_result", "thinking"}.
    """
    model = model or _detect_model()
    if not model:
        return {"answer": "本地大模型未运行(:8001)。请先 `make llm`。", "steps": 0, "model": None, "messages": []}

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})

    tool_trace: list[dict] = []
    for step in range(MAX_STEPS):
        resp = _chat(messages, model, tools=TOOL_SCHEMAS)
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {"answer": msg.get("content") or "", "steps": step, "model": model,
                    "messages": messages, "tools_used": tool_trace}
        # Record the assistant tool-call turn verbatim (required for the next round).
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if on_event:
                on_event("tool_call", {"name": name, "args": args})
            result = execute_tool(name, args)
            tool_trace.append({"name": name, "args": args})
            if on_event:
                on_event("tool_result", {"name": name, "result": result[:300]})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", name), "content": result})

    # Hit the step cap — ask for a final synthesis without more tools.
    messages.append({"role": "user", "content": "请基于以上工具结果,用中文给出最终回答。"})
    resp = _chat(messages, model, tools=None)
    return {"answer": resp["choices"][0]["message"].get("content") or "", "steps": MAX_STEPS,
            "model": model, "messages": messages, "tools_used": tool_trace}
