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
MAX_STEPS = 6
MAX_RETRIES = 1  # reflect -> retry budget per question

SYSTEM_PROMPT = (
    "你是 SciScope 科研文献智能体,可访问一个 16 万篇科技文献的知识库。"
    "你拥有以下工具:search_literature(检索论文)、get_trends(研究趋势)、"
    "recommend_papers(相似论文推荐,需 paper_id)、get_paper(论文详情)、"
    "query_knowledge_graph(知识图谱/研究社区)、verify_claim(用语义接地度核查论断是否有文献支持)。"
    "工作方式:① 对复杂问题先规划需要哪些检索步骤,再依次调用工具(可多步);"
    "recommend_papers/get_paper/compare_papers 需要真实 paper_id——必须先用 search_literature 拿到,"
    "严禁编造 paper_id;② 凡涉及文献事实的问题,必须先调用工具检索证据,不能凭记忆直接回答;"
    "若同一工具同参数已调用过,不要重复调用,改用不同参数或据已有结果作答;"
    "③ 拿到工具结果后用中文综合归纳作答,只依据工具返回的真实数据,不编造,证据不足时如实说明。"
    "注意:检索结果里的「摘要片段」是论文摘要节选,「作者」才是作者。"
    "④ 用结构化 Markdown 作答,层次清晰:先一句话概述结论;再用有序列表分点,"
    "每点以 **加粗论文标题**(年份)开头并简述其贡献;需要时用 `##` 小标题分组(如「代表工作」「研究趋势」);"
    "最后用一句 `> ` 引用块给出小结或趋势判断。避免大段连续文字。"
)

# Answers that signal the retrieval/answer was inadequate — trigger one retry.
_WEAK_ANSWER = ("没有找到", "未找到", "未检索到", "无法回答", "无法确定", "抱歉",
                "没有相关", "缺乏", "无相关信息", "i don't", "cannot find", "no relevant")
# Greetings / meta / capability questions that legitimately need no tools.
_META = ("你好", "您好", "你是谁", "你是什么", "你能做什么", "你能干什么", "你会什么",
         "自我介绍", "介绍一下你", "怎么用", "如何使用", "帮助", "谢谢", "多谢", "再见",
         "hello", "hi ", "who are you", "what can you", "help", "thanks")


def _reflect_reason(answer: str, tools_used: int, question: str) -> str | None:
    """Decide whether to self-correct: returns a retry instruction, or None.

    Two failure modes worth one retry: (a) a *fact-seeking* question answered with
    zero tool calls (possible hallucination), (b) the answer admits it lacked
    evidence. Greetings / meta / capability questions are exempt (no tools needed).
    """
    a = (answer or "").lower()
    q = question.strip().lower()
    is_meta = len(q) < 4 or any(m in q for m in _META)
    if tools_used == 0 and not is_meta:
        return "你没有调用任何工具就回答了。请先用 search_literature 等工具检索证据,再据实回答。"
    if any(w in a for w in _WEAK_ANSWER):
        return "上次检索证据不足。请换用不同的关键词(或英文术语)重新检索,再回答。"
    return None


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


_REPEAT_NOTE = "(已用相同参数调用过该工具,结果同上。请改用不同参数或其他工具,或据已有结果作答,不要重复调用。)"


def _run_tools(tool_calls: list[dict], executed: dict[str, str]) -> list[str]:
    """Execute a step's tool calls in parallel (all SciScope tools are read-only).

    ``executed`` caches results by (name, arguments) signature across steps: an
    identical repeat is short-circuited with a note instead of re-running, which
    breaks the failure mode where the model re-issues the same broken call (e.g. a
    fabricated paper_id) every step until the step cap.
    """
    def one(tc: dict) -> str:
        sig = tc["function"]["name"] + "|" + (tc["function"].get("arguments") or "{}")
        if sig in executed:
            return _REPEAT_NOTE
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        result = execute_tool(tc["function"]["name"], args)
        executed[sig] = result
        return result

    if len(tool_calls) == 1:
        return [one(tool_calls[0])]
    with ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as pool:
        return list(pool.map(one, tool_calls))


# Questions worth an explicit plan (multi-step / comparative / synthesis tasks).
# Simple lookups and greetings skip planning to avoid a wasted LLM round-trip.
_PLAN_MARKERS = (
    "对比", "比较", "区别", "差异", "相比", "异同", "综述", "研究现状", "概览",
    "趋势", "演进", "演变", "发展", "推荐", "关系", "哪些", "梳理", "总结", "现状",
    "vs", "versus", "compare", "review", "survey", "trend", "recommend",
)


def _needs_plan(question: str) -> bool:
    q = question.strip().lower()
    if len(q) < 4 or any(m in q for m in _META):
        return False
    return any(m in q for m in _PLAN_MARKERS) or len(question) >= 18


def _parse_plan(text: str) -> list[str]:
    """Extract numbered/bulleted steps from a planning completion (pure, testable)."""
    steps: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip().lstrip("-*·•0123456789.、)（) ").strip()
        core = s.rstrip(":：").strip()
        if len(s) >= 3 and core and core.lower() not in ("计划", "plan", "步骤", "steps"):
            steps.append(s)
    return steps[:4]


def _complete(messages: list[dict], model: str) -> str:
    """Drain a non-streaming completion (no tools) to a single string."""
    text, _ = _drain(_stream_chat(messages, model, None), lambda k, p: None)
    return text


def _make_plan(question: str, model: str) -> list[str]:
    """Ask the model to decompose a complex question into 2-4 executable steps."""
    prompt = [
        {"role": "system", "content": "你是科研智能体的规划器,只输出执行步骤。"},
        {"role": "user", "content": (
            "把下面的科研问题拆成 2-4 个可执行步骤。每步只能使用以下内置工具之一,"
            "并写清用它检索/处理什么:\n"
            "search_literature(检索文献)、get_trends(研究趋势)、recommend_papers(相似推荐)、"
            "get_paper(论文详情)、summarize_field(领域综述)、compare_papers(论文对比)、"
            "query_knowledge_graph(知识图谱)、verify_claim(论断核查)。\n"
            "不要使用 Google Scholar、Web of Science 等外部工具。"
            "注意:recommend_papers/get_paper/compare_papers 依赖 paper_id,必须先安排一步 "
            "search_literature 才能拿到 id,不能直接对主题词调用它们。"
            "每行一步,只输出步骤本身,不要解释、不要编号前缀。\n\n"
            f"问题:{question}\n\n步骤:"
        )},
    ]
    try:
        return _parse_plan(_complete(prompt, model))
    except Exception:  # noqa: BLE001 — planning is best-effort; never break the loop
        return []


def _self_critique(question: str, answer: str, model: str) -> str | None:
    """Model-driven reflection: have the model judge whether its own answer is
    sufficient and evidence-grounded. Returns a retry instruction, or None if OK.
    """
    prompt = [
        {"role": "system", "content": "你是严格的审稿人,只输出 OK 或 RETRY。"},
        {"role": "user", "content": (
            f"问题:{question}\n\n回答:{answer}\n\n"
            "判断这个回答是否充分回答了问题、且关键论断都有文献证据支撑。"
            "若充分且有据,只回复 OK;否则回复「RETRY:」加一句话指出缺什么、该补检索什么。"
        )},
    ]
    try:
        out = _complete(prompt, model).strip()
    except Exception:  # noqa: BLE001
        return None
    if out.upper().startswith("RETRY"):
        reason = out.split(":", 1)[-1].split("：", 1)[-1].strip()
        return reason or "回答证据不足,请补充检索后重答。"
    return None


def stream_agent(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
) -> Iterator[tuple[str, Any]]:
    """Event stream for the agentic loop. Yields:
    ('plan', [steps]) | ('text', delta) | ('tool_call', {name,args}) |
    ('tool_result', {name,result}) | ('reflect', reason) | ('final', answer).
    """
    model = model or _detect_model()
    if not model:
        yield ("final", "本地大模型未运行(:8001)。请先 `make llm`。")
        return

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})

    # Explicit planning: for complex tasks, the model first emits a step plan.
    # The plan is surfaced as an event (shown in the UI / report) and primed into
    # context so the loop executes it — this is what makes it a real agent, not a
    # one-shot answerer.
    if _needs_plan(question):
        plan = _make_plan(question, model)
        if plan:
            yield ("plan", plan)
            messages.append({"role": "assistant",
                             "content": "执行计划:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(plan, 1))})
            messages.append({"role": "user", "content": "请按上述计划逐步调用工具完成,最后用中文综合作答。"})

    text_events: list[tuple[str, Any]] = []
    forward = lambda k, p: text_events.append((k, p))  # noqa: E731
    tools_total = 0
    retries = 0
    executed: dict[str, str] = {}  # (name|args) -> result, dedup repeats across steps

    for _ in range(MAX_STEPS):
        _compact(messages)
        text_events.clear()
        full_text, tool_calls = _drain(_stream_chat(messages, model, TOOL_SCHEMAS), forward)
        for ev in text_events:
            yield ev
        if not tool_calls:
            # Reflect: self-correct once if the answer is ungrounded/insufficient.
            # (1) cheap heuristic catches the obvious no-tool hallucination / weak
            # answer; (2) if it passes but the answer was tool-grounded, let the
            # model critique its own sufficiency.
            reason = None
            if retries < MAX_RETRIES:
                reason = _reflect_reason(full_text, tools_total, question)
                if reason is None and tools_total > 0:
                    reason = _self_critique(question, full_text, model)
            if reason:
                retries += 1
                yield ("reflect", reason)
                messages.append({"role": "assistant", "content": full_text})
                messages.append({"role": "user", "content": (
                    reason + " 请直接据此重新检索并给出改进后的【完整中文回答】,"
                    "不要回复「好的」、不要复述计划或描述你将要做什么。"
                )})
                continue
            yield ("final", full_text)
            return
        messages.append({"role": "assistant", "content": full_text, "tool_calls": tool_calls})
        tools_total += len(tool_calls)
        for tc in tool_calls:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            yield ("tool_call", {"name": tc["function"]["name"], "args": args})
        results = _run_tools(tool_calls, executed)
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
