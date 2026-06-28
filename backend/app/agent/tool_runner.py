"""Tool execution primitives shared by agent runtimes."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from backend.app.agent.tools import execute_tool, is_read_only


REPEAT_NOTE = "(已用相同参数调用过该工具,结果同上。请改用不同参数或其他工具,或据已有结果作答,不要重复调用。)"

# (tool_name, progress_message) — emitted while a streaming tool runs.
ProgressFn = Callable[[str, str], None]


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
        result = execute_tool(name, args, on_progress=progress)
        executed[sig] = result
        return result

    # Only parallelize when every call is read-only/concurrency-safe; a future
    # write tool in the batch forces sequential execution.
    all_read_only = all(is_read_only(tc["function"]["name"]) for tc in tool_calls)
    if len(tool_calls) == 1 or not all_read_only:
        return [one(tool_call) for tool_call in tool_calls]
    with ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as pool:
        return list(pool.map(one, tool_calls))
