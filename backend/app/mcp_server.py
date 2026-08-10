"""SciScope exposed as an MCP server.

Publishes the SciScope research tools — the *same* registry the agent uses — over
the Model Context Protocol, so any MCP client (Claude Desktop, Cursor, Codex, …)
can ground on the 160k-paper corpus, run trend/recommendation analysis, and
fact-check claims with ``verify_claim``.

This is a thin adapter: it reuses the ``Tool`` contract (each tool's JSON schema)
and the ``execute_tool`` dispatch — no tool logic is duplicated. Adding a tool to
the agent automatically exposes it here too.

Run (stdio transport)::

    python -m backend.app.mcp_server

Then point an MCP client at that command. See docs/mcp.md.
"""

from __future__ import annotations

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server

from backend.app.agent.tools import TOOLS, execute_tool
from backend.app.services.stance.store import disputed_claims

SERVER_NAME = "sciscope"


async def _list_tools() -> list[types.Tool]:
    """Advertise every SciScope tool, carrying its JSON schema straight through."""
    return [
        types.Tool(
            name=tool.name,
            description=tool.schema["function"]["description"],
            inputSchema=tool.schema["function"]["parameters"],
        )
        for tool in TOOLS
    ]


async def _call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Dispatch to the shared execute_tool (validation + run + bounded result).

    execute_tool is synchronous (DB / embedder / network), so it runs in a thread
    to keep the MCP event loop responsive. It always returns a display string
    (validation rejections and errors included), so clients get a readable result.
    """
    result = await asyncio.to_thread(execute_tool, name, arguments or {})
    return [types.TextContent(type="text", text=result)]


_DISPUTES_URI = "sciscope://disputes/recent"


async def _list_resources() -> list[types.Resource]:
    """Advertise the dispute frontier as a discoverable MCP data resource."""
    return [
        types.Resource(
            uri=_DISPUTES_URI,
            name="SciScope 科学争议前线",
            description="具有可采信正反证据的论断；空结果不表示科学上不存在争议。",
            mimeType="application/json",
        )
    ]


async def _read_resource(uri) -> list[ReadResourceContents]:
    """Serve only the fixed, read-only dispute-frontier resource."""
    if str(uri) != _DISPUTES_URI:
        raise ValueError(f"Unknown resource: {uri}")
    rows = await asyncio.to_thread(disputed_claims, 20)
    payload = {
        "count": len(rows),
        "disputes": rows,
        "boundary": "Only accepted SUPPORT/CONTRADICT evidence is included.",
    }
    return [ReadResourceContents(content=json.dumps(payload, ensure_ascii=False), mime_type="application/json")]


server: Server = Server(SERVER_NAME)
server.list_tools()(_list_tools)
server.call_tool()(_call_tool)
server.list_resources()(_list_resources)
server.read_resource()(_read_resource)


def main() -> None:
    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
