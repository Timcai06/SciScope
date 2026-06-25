"""Tool execution primitives shared by agent runtimes."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from backend.app.agent.tools import execute_tool


REPEAT_NOTE = "(已用相同参数调用过该工具,结果同上。请改用不同参数或其他工具,或据已有结果作答,不要重复调用。)"


def run_tools(tool_calls: list[dict], executed: dict[str, str]) -> list[str]:
    """Execute read-only SciScope tool calls and deduplicate exact repeats."""

    def one(tool_call: dict) -> str:
        sig = tool_call["function"]["name"] + "|" + (tool_call["function"].get("arguments") or "{}")
        if sig in executed:
            return REPEAT_NOTE
        try:
            args = json.loads(tool_call["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        result = execute_tool(tool_call["function"]["name"], args)
        executed[sig] = result
        return result

    if len(tool_calls) == 1:
        return [one(tool_calls[0])]
    with ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as pool:
        return list(pool.map(one, tool_calls))
