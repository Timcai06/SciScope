# SciScope as an MCP server

SciScope exposes its research tools over the **Model Context Protocol (MCP)**, so
any MCP client — Claude Desktop, Cursor, Codex, etc. — can ground on the
~160k-paper corpus, run trend/recommendation analysis, and fact-check claims,
without going through the SciScope agent or TUI.

It is a thin adapter (`backend/app/mcp_server.py`): it reuses the agent's `Tool`
registry (the same JSON schemas) and the shared `execute_tool` dispatch, so the
exposed tools always match the agent's tools — no duplication, no drift.

## Tools exposed

All 9 SciScope tools: `search_literature`, `get_trends`, `recommend_papers`,
`get_paper`, `summarize_field`, `compare_papers`, `export_bibliography`,
`query_knowledge_graph`, `verify_claim`. Each carries its JSON input schema; the
pre-execution validation gate (e.g. rejecting fabricated `paper_id`s) applies
here too.

## Run

```bash
make mcp                       # stdio transport
# equivalently: python -m backend.app.mcp_server
```

It needs the same runtime as the backend: `SCISCOPE_DB_DSN` + the embedder for
retrieval/grounding tools (otherwise those return a readable "DB unavailable"
string). Trend/graph tools read the local model/graph files.

## Connect Claude Desktop

Add to Claude Desktop's MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sciscope": {
      "command": "/opt/homebrew/Caskroom/miniconda/base/envs/ai/bin/python",
      "args": ["-m", "backend.app.mcp_server"],
      "cwd": "/path/to/数据要素",
      "env": {
        "SCISCOPE_DB_DSN": "postgresql://USER@localhost:5432/sciscope",
        "SCISCOPE_EMBEDDER_PATH": "models/embedder_local/multilingual-e5-base"
      }
    }
  }
}
```

Restart Claude Desktop; the SciScope tools appear in the tool picker. Asking
"verify: RAG reduces hallucination, search our corpus" will call `verify_claim`
/ `search_literature` against the local corpus.

## Boundary

This server is the **generation-agnostic** face of SciScope: it provides grounded
*tools*, not an agent loop. The client's own model decides when to call them. The
SciScope agent (LangGraph) and the MCP server share the same tool layer but are
independent entry points.

---

# Consuming external MCP servers (direction ②)

The SciScope agent can also go the other way: use tools from **external** MCP
servers. Declare them in `configs/mcp_servers.json` (copy
`configs/mcp_servers.json.example`):

```json
{
  "servers": {
    "fetch": { "command": "uvx", "args": ["mcp-server-fetch"], "env": {} }
  }
}
```

At backend startup (`make backend`), each server's tools are discovered and
wrapped as agent tools named `mcp__<server>__<tool>`, merged into the same
registry the agent and `execute_tool` use — so the model can call them like any
native tool. No config file = nothing happens (no external processes).

`backend/app/agent/mcp_client.py` is the adapter: it lists/calls remote tools
over stdio (async bridged to our sync tool layer per call) and wraps them via the
`Tool` contract. External tools are marked non-read-only (run sequentially,
conservative). This means new capabilities (web fetch, web search, etc.) are
added by **plugging an MCP server**, not by writing native tool code — keeping the
9 native tools focused on the curated corpus.

Verified by loopback: pointing the consumer at SciScope's own MCP server (①)
discovers all 9 tools and calls them successfully.

---

# Specialist sub-agents (direction ③)

The agent can delegate a focused subtask to a **role-specialized sub-agent** via
the `delegate` tool (`backend/app/agent/specialists.py`) — mirroring Claude Code's
AgentTool (sub-agents spawned like a tool call):

| role | 专员 | tool subset |
|---|---|---|
| `reviewer` | 综述员 | search_literature, summarize_field, get_paper |
| `trend` | 趋势分析师 | get_trends, search_literature |
| `critic` | 批判核查员 | verify_claim, search_literature |

The main agent (coordinator) calls `delegate(role, task)` for complex,
multi-faceted requests (e.g. "review X and fact-check its key claims"); each
specialist runs a bounded tool loop with its own system prompt and restricted
tools. **Recursion is structurally impossible** — specialist tool subsets never
include `delegate`, so a sub-agent cannot spawn further sub-agents.
