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
