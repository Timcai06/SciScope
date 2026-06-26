"""Consume external MCP servers as SciScope agent tools (MCP direction ②).

Connects to MCP servers declared in a config file, lists their tools, and wraps
each as a SciScope ``Tool`` so the agent calls them through the same contract and
``execute_tool`` dispatch as native tools. External tools are namespaced
``mcp__<server>__<tool>`` to avoid collisions.

Activation is opt-in: drop a config at ``configs/mcp_servers.json`` (or point
``SCISCOPE_MCP_CONFIG`` at one) and call :func:`activate_mcp_tools` (the backend
does this at startup when a config exists). No config = no external processes.

Config format::

    {"servers": {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"], "env": {}}}}

Async MCP I/O is bridged to the sync tool layer with a short-lived stdio session
per call — simple and correct; a connection pool can come later if needed.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.app.agent.tools import Tool, register_tools

CONFIG_PATH = Path(os.getenv("SCISCOPE_MCP_CONFIG", "configs/mcp_servers.json"))


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _run_session(spec: dict[str, Any], fn: Callable[[Any], Awaitable[Any]]) -> Any:
    """Open a short-lived stdio MCP session for one operation, synchronously."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=spec["command"],
        args=spec.get("args", []),
        env={**os.environ, **(spec.get("env") or {})},
    )

    async def _go() -> Any:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)

    return asyncio.run(_go())


def list_remote_tools(spec: dict[str, Any]) -> list[dict[str, Any]]:
    async def _fn(session: Any) -> list[dict[str, Any]]:
        result = await session.list_tools()
        return [
            {"name": t.name, "description": t.description or "", "schema": t.inputSchema or {}}
            for t in result.tools
        ]

    return _run_session(spec, _fn)


def call_remote_tool(spec: dict[str, Any], tool_name: str, args: dict[str, Any]) -> str:
    async def _fn(session: Any) -> str:
        result = await session.call_tool(tool_name, args or {})
        texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
        return "\n".join(texts) if texts else "(MCP 工具无文本返回)"

    try:
        return _run_session(spec, _fn)
    except Exception as exc:  # noqa: BLE001 — surface to the model like any tool error
        return f"外部 MCP 工具 {tool_name} 调用失败: {type(exc).__name__}: {exc}"


def _wrap(server_name: str, spec: dict[str, Any], remote: dict[str, Any]) -> Tool:
    full_name = f"mcp__{server_name}__{remote['name']}"
    schema = remote.get("schema") or {"type": "object", "properties": {}}
    return Tool(
        name=full_name,
        schema={
            "type": "function",
            "function": {
                "name": full_name,
                "description": f"[{server_name}] {remote.get('description', '')}".strip(),
                "parameters": schema,
            },
        },
        run=lambda args, _spec=spec, _name=remote["name"]: call_remote_tool(_spec, _name, args),
        is_read_only=False,  # external side effects unknown → run sequentially, be conservative
        prompt_fragment=f"(外部 MCP·{server_name}){remote.get('description', '')}"[:80],
    )


def load_mcp_tools() -> list[Tool]:
    """Discover and wrap tools from every configured MCP server."""
    config = _load_config()
    tools: list[Tool] = []
    for server_name, spec in (config.get("servers") or {}).items():
        if not isinstance(spec, dict) or not spec.get("command"):
            continue
        try:
            remote_tools = list_remote_tools(spec)
        except Exception:  # noqa: BLE001 — a bad server shouldn't break startup
            continue
        tools.extend(_wrap(server_name, spec, rt) for rt in remote_tools)
    return tools


def activate_mcp_tools() -> list[str]:
    """Load configured external MCP tools and merge them into the agent registry."""
    return register_tools(load_mcp_tools())
