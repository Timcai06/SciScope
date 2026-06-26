"""SciScope MCP server adapter — exposes the agent's tool registry over MCP."""

from __future__ import annotations

import asyncio

from backend.app import mcp_server
from backend.app.agent.tools import TOOLS


def test_lists_every_agent_tool_with_schema():
    tools = asyncio.run(mcp_server._list_tools())
    assert {t.name for t in tools} == {t.name for t in TOOLS}
    assert len(tools) == len(TOOLS)
    search = next(t for t in tools if t.name == "search_literature")
    assert "query" in (search.inputSchema.get("properties") or {})
    assert search.description  # carried from the tool schema


def test_call_tool_returns_text_content():
    out = asyncio.run(mcp_server._call_tool("verify_claim", {"claim": ""}))
    assert len(out) == 1
    assert out[0].type == "text"
    assert "claim" in out[0].text  # verify_claim's empty-input message


def test_call_tool_applies_validation_gate():
    # Fabricated paper_id is rejected by the shared validate gate — no DB needed.
    out = asyncio.run(mcp_server._call_tool("recommend_papers", {"paper_id": "machine learning"}))
    assert out[0].text.startswith("[未执行]")


def test_unknown_tool_is_reported_not_raised():
    out = asyncio.run(mcp_server._call_tool("nope", {}))
    assert out[0].text == "未知工具: nope"
