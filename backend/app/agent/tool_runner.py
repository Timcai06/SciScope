"""Tool execution primitives shared by agent runtimes."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from backend.app.agent.tools import execute_tool, is_read_only


REPEAT_NOTE = "(已用相同参数调用过该工具,结果同上。请改用不同参数或其他工具,或据已有结果作答,不要重复调用。)"

# (tool_name, progress_message) — emitted while a streaming tool runs.
ProgressFn = Callable[[str, str], None]

# Result-list tools whose entries carry a paper_id — candidates for cross-query
# paper dedup (different keywords often return the same top papers).
_SEARCH_TOOLS = {"search_literature", "recommend_papers"}


def _known_paper_ids(executed: dict[str, str]) -> set[str]:
    """paper_ids already shown to the model this turn, from prior tool results."""
    seen: set[str] = set()
    for result in executed.values():
        try:
            data = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("paper_id"):
                seen.add(str(item["paper_id"]))
            # One nested level: verify_claim wraps its papers in a 证据 list.
            for value in item.values():
                if isinstance(value, list):
                    for sub in value:
                        if isinstance(sub, dict) and sub.get("paper_id"):
                            seen.add(str(sub["paper_id"]))
    return seen


def _dedupe_papers(result: str, seen: set[str]) -> str:
    """Compact papers the model has already seen this turn into a one-line note.

    A repeated paper burns context and reads as fresh evidence; replacing it with
    an explicit "already shown" note both saves tokens and tells the model that
    rewording the query is not surfacing new papers.
    """
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return result
    if not isinstance(data, list) or not data:
        return result
    fresh = [d for d in data if not (isinstance(d, dict) and str(d.get("paper_id")) in seen)]
    dup_count = len(data) - len(fresh)
    if dup_count == 0:
        return result
    if not fresh:
        return (
            f"本次检索的 {dup_count} 篇论文全部与本轮此前结果重复,没有新证据。"
            "请换一个明显不同的检索角度,或直接基于已有证据作答。"
        )
    payload: list = [*fresh, {"提示": f"另有 {dup_count} 篇论文与本轮此前结果重复,已省略。"}]
    return json.dumps(payload, ensure_ascii=False)


def run_tools(
    tool_calls: list[dict],
    executed: dict[str, str],
    on_progress: ProgressFn | None = None,
) -> list[str]:
    """Execute read-only SciScope tool calls and deduplicate exact repeats.

    ``on_progress`` (optional) is called ``(tool_name, message)`` for each progress
    string a streaming tool yields, so runtimes can surface a live tool timeline.
    """

    def one(tool_call: dict) -> str:
        name = tool_call["function"]["name"]
        sig = name + "|" + (tool_call["function"].get("arguments") or "{}")
        if sig in executed:
            return REPEAT_NOTE
        try:
            args = json.loads(tool_call["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        progress = (lambda message: on_progress(name, message)) if on_progress else None
        # Snapshot known papers before executing so a tool's own result isn't
        # deduped against itself.
        seen = _known_paper_ids(executed) if name in _SEARCH_TOOLS else set()
        result = execute_tool(name, args, on_progress=progress)
        if name in _SEARCH_TOOLS:
            result = _dedupe_papers(result, seen)
        executed[sig] = result
        return result

    # Only parallelize when every call is read-only/concurrency-safe; a future
    # write tool in the batch forces sequential execution.
    all_read_only = all(is_read_only(tc["function"]["name"]) for tc in tool_calls)
    if len(tool_calls) == 1 or not all_read_only:
        return [one(tool_call) for tool_call in tool_calls]
    with ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as pool:
        return list(pool.map(one, tool_calls))


MISSING_RESULT_NOTE = "(工具结果缺失:上一步被中断或出错,请据现有信息继续作答。)"


def _tool_call_id(tool_call: dict) -> str:
    return tool_call.get("id") or tool_call["function"]["name"]


def repair_missing_tool_results(messages: list[dict]) -> int:
    """Ensure every ``tool_call`` in an assistant message is immediately followed by a
    matching tool result, synthesizing a placeholder for any that is missing.

    Mirrors Claude Code's ``yieldMissingToolResultBlocks``: an interrupted or failed
    tool step can leave an assistant ``tool_calls`` block without its ``tool`` reply,
    which violates the chat API contract (every tool call needs a result) and makes
    the next request fail. This repairs the message list in place before the call.
    Returns the number of placeholders inserted.
    """
    repaired = 0
    out: list[dict] = []
    i = 0
    while i < len(messages):
        message = messages[i]
        out.append(message)
        i += 1
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            continue
        # Consume the tool results that immediately follow this assistant message.
        answered: set[str] = set()
        while i < len(messages) and messages[i].get("role") == "tool":
            out.append(messages[i])
            answered.add(messages[i].get("tool_call_id"))
            i += 1
        # Fill any tool call that did not get a result, preserving order/adjacency.
        for tool_call in message["tool_calls"]:
            tcid = _tool_call_id(tool_call)
            if tcid not in answered:
                out.append({"role": "tool", "tool_call_id": tcid, "content": MISSING_RESULT_NOTE})
                repaired += 1
    messages[:] = out
    return repaired
