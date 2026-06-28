"""SciScope agent tools: each capability is a self-contained ``Tool`` module.

This package mirrors Claude Code's ``tools/`` layout — one module per tool, each
co-locating its schema, handler, validation and "when to use me" prompt — over a
shared contract/registry engine (:mod:`base`). Adding a capability is dropping a
module here and listing its ``TOOL`` below; the agent loop never changes.

Boundary note: native tools are read-only and map to backend service/table state
(papers/chunks/chunk_embeddings/recommendation assets/graphs). Returned payloads
are evidence references, not raw authoritative facts.
"""

from __future__ import annotations

from backend.app.agent.tools.base import (
    Tool,
    TOOL_SCHEMAS,
    _REGISTRY,
    check_permission,
    execute_tool,
    get_tool,
    invoke_tool,
    is_read_only,
    register_tools,
    side_effect_of,
    tools_prompt,
)
from backend.app.agent.tools._validators import validate_paper_id
from backend.app.agent.tools.hooks import (
    HookResult,
    ToolHookContext,
    clear_hooks,
    register_hook,
)
from backend.app.agent.tools import (
    compare_papers,
    delegate,
    export_bibliography,
    get_paper,
    get_trends,
    query_knowledge_graph,
    recommend_papers,
    search_literature,
    summarize_field,
    verify_claim,
)

# Native tool set. Order is the catalog/schema order the model sees.
NATIVE_TOOLS: list[Tool] = [
    search_literature.TOOL,
    get_trends.TOOL,
    recommend_papers.TOOL,
    get_paper.TOOL,
    summarize_field.TOOL,
    compare_papers.TOOL,
    export_bibliography.TOOL,
    query_knowledge_graph.TOOL,
    verify_claim.TOOL,
    delegate.TOOL,
]

register_tools(NATIVE_TOOLS)

# Snapshot of the native tool set (external MCP tools register later via
# register_tools and are reachable through _REGISTRY / TOOL_SCHEMAS, not here).
TOOLS: tuple[Tool, ...] = tuple(NATIVE_TOOLS)

# Backwards-compatible alias for the previous flat-module name.
_validate_paper_id = validate_paper_id

__all__ = [
    "Tool",
    "TOOL_SCHEMAS",
    "TOOLS",
    "NATIVE_TOOLS",
    "execute_tool",
    "invoke_tool",
    "is_read_only",
    "side_effect_of",
    "check_permission",
    "get_tool",
    "register_tools",
    "tools_prompt",
    "validate_paper_id",
    "register_hook",
    "clear_hooks",
    "HookResult",
    "ToolHookContext",
]
