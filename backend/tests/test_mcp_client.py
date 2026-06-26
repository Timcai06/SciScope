"""Consuming external MCP servers as agent tools (MCP direction ②)."""

from __future__ import annotations

from backend.app.agent import mcp_client
from backend.app.agent.tools import execute_tool, is_read_only


def test_wraps_remote_tool_into_namespaced_agent_tool():
    tool = mcp_client._wrap(
        "fetch",
        {"command": "uvx", "args": ["mcp-server-fetch"]},
        {"name": "fetch", "description": "fetch a URL", "schema": {"type": "object", "properties": {"url": {"type": "string"}}}},
    )
    assert tool.name == "mcp__fetch__fetch"
    assert tool.is_read_only is False  # external side effects unknown
    assert "fetch a URL" in tool.schema["function"]["description"]
    assert tool.schema["function"]["parameters"]["properties"]["url"]["type"] == "string"


def test_load_mcp_tools_empty_without_config(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_client, "CONFIG_PATH", tmp_path / "absent.json")
    assert mcp_client.load_mcp_tools() == []


def test_load_and_register_merges_into_agent_registry(monkeypatch):
    # Stub remote discovery + call so no real MCP server is spawned.
    fake = [{"name": "echo", "description": "echo text", "schema": {"type": "object", "properties": {"text": {"type": "string"}}}}]
    monkeypatch.setattr(mcp_client, "_load_config", lambda: {"servers": {"demo": {"command": "x"}}})
    monkeypatch.setattr(mcp_client, "list_remote_tools", lambda spec: fake)
    monkeypatch.setattr(mcp_client, "call_remote_tool", lambda spec, name, args: f"ECHO:{args.get('text')}")

    added = mcp_client.activate_mcp_tools()
    try:
        assert "mcp__demo__echo" in added
        # The agent can now dispatch the external tool through execute_tool.
        assert execute_tool("mcp__demo__echo", {"text": "hi"}) == "ECHO:hi"
        assert is_read_only("mcp__demo__echo") is False
    finally:
        # Clean the registry so other tests see only native tools.
        from backend.app.agent import tools as tools_mod

        tools_mod._REGISTRY.pop("mcp__demo__echo", None)
        tools_mod.TOOL_SCHEMAS[:] = [s for s in tools_mod.TOOL_SCHEMAS if s["function"]["name"] != "mcp__demo__echo"]
