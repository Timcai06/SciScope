"""Tool contract + registry engine for the SciScope agent.

This is the SciScope analog of Claude Code's ``Tool`` abstraction: each capability
is a self-describing object that declares its own input schema, concurrency safety
(via ``side_effect``), pre-execution validation, permission gate, result-size
bound, and "when to use me" prompt fragment. The agent loop stays thin because it
never special-cases an individual tool — adding a capability is registering a
``Tool``, not growing the orchestration code.

Three cross-cutting concerns live here, mirroring Claude Code:

* **Permissions** (``check_permission`` ~ Claude Code's ``checkPermissions``):
  a deterministic gate run *before* validation/execution. Read-only and opt-in
  external (MCP) tools pass; data-mutating tools are denied unless writes are
  explicitly enabled — so a future write tool can be added without touching the
  loop.
* **Streaming progress** (``invoke_tool`` ~ Claude Code's ``async *call()``):
  a tool's ``run`` may be an ordinary function returning a string, or a generator
  that ``yield``s human-readable progress strings and ``return``s the final
  result. Progress is forwarded to an optional callback.
* **Catalog assembly** (``tools_prompt``): the tool list the model sees is built
  from each tool's ``prompt_fragment`` so it never drifts from the actual set.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Literal

SideEffect = Literal["read", "write", "external"]

# Policy switch for data-mutating tools. Off by default: SciScope's native tools
# are all read-only evidence lookups, so nothing is gated today — but the gate is
# in place so a write tool added later is denied until writes are deliberately
# enabled, instead of the loop having to special-case it.
ALLOW_WRITE_TOOLS = False


@dataclass(frozen=True)
class Tool:
    """A SciScope capability as a first-class, self-contained contract.

    ``run`` is either ``(args) -> str`` or a generator ``(args)`` that yields
    progress strings and returns the final result string. Either way the runtime
    treats it uniformly via :func:`invoke_tool`.
    """

    name: str
    schema: dict[str, Any]
    run: Callable[[dict[str, Any]], Any]
    # How the tool touches the world. Drives both concurrency (only "read" tools
    # run in parallel) and the permission gate. "external" = opt-in MCP tool with
    # unknown side effects: run sequentially but allowed (the user configured it).
    side_effect: SideEffect = "read"
    # Deterministic input check. Returns a recovery message (and skips execution),
    # or None to proceed. Distinct from the permission gate below.
    validate: Callable[[dict[str, Any]], str | None] | None = None
    # Permission gate (Claude Code's checkPermissions analog). Returns a denial
    # reason or None. When omitted, the default side-effect policy applies.
    check_permissions: Callable[[dict[str, Any]], str | None] | None = None
    max_result_chars: int = 8000
    # One-line "when to use me", assembled into the system prompt's tool catalog.
    prompt_fragment: str = ""

    @property
    def is_read_only(self) -> bool:
        """Concurrency-safe iff the tool only reads — used by the parallel runner."""
        return self.side_effect == "read"


# --- Registry ---------------------------------------------------------------
# Mutable module state so register_tools() (e.g. wrapped external MCP tools) and
# the agent loop (which imports TOOL_SCHEMAS by reference) see the same objects.
_REGISTRY: dict[str, Tool] = {}
TOOL_SCHEMAS: list[dict[str, Any]] = []


def register_tools(extra: list[Tool]) -> list[str]:
    """Merge tools into the shared registry + TOOL_SCHEMAS in place.

    Used both for the native tool set at import time and for dynamically
    discovered tools (wrapped external MCP servers). The runtime never changes;
    it just sees more entries. Returns the names actually added.
    """
    added: list[str] = []
    for tool in extra:
        if tool.name in _REGISTRY:
            continue
        _REGISTRY[tool.name] = tool
        TOOL_SCHEMAS.append(tool.schema)
        added.append(tool.name)
    return added


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def is_read_only(name: str) -> bool:
    """Whether a tool may run concurrently with others (default True if unknown)."""
    tool = _REGISTRY.get(name)
    return tool.is_read_only if tool else True


def side_effect_of(name: str) -> SideEffect:
    tool = _REGISTRY.get(name)
    return tool.side_effect if tool else "read"


def tools_prompt() -> str:
    """Assemble the tool catalog for the system prompt from each tool's fragment.

    Mirrors Claude Code's per-tool self-description: the catalog the model sees is
    built from the registry, so it never drifts from the actual tool set.
    """
    return "\n".join(
        f"- {t.name}:{t.prompt_fragment}" for t in _REGISTRY.values() if t.prompt_fragment
    )


# --- Permission gate --------------------------------------------------------
def check_permission(tool: Tool, args: dict[str, Any]) -> str | None:
    """Decide whether a tool may run. Returns a denial reason, or None to allow.

    Per-tool ``check_permissions`` wins; otherwise the default side-effect policy
    applies: reads and opt-in external tools are allowed, data writes are denied
    unless ``ALLOW_WRITE_TOOLS`` is enabled.
    """
    if tool.check_permissions is not None:
        return tool.check_permissions(args)
    if tool.side_effect == "write" and not ALLOW_WRITE_TOOLS:
        return (
            f"工具 {tool.name} 会修改数据,但当前为只读模式,未授权执行。"
            "(如确需写操作,请在受控环境开启写权限。)"
        )
    return None


# --- Execution --------------------------------------------------------------
def invoke_tool(
    tool: Tool,
    args: dict[str, Any],
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Run a tool's handler uniformly, whether it streams progress or not.

    Generator handlers yield progress strings (forwarded to ``on_progress``) and
    return the final result; plain handlers just return their result. Mirrors
    Claude Code's ``async *call()`` progress protocol in a sync world.
    """
    fn = tool.run
    if inspect.isgeneratorfunction(fn):
        gen: Iterator[str] = fn(args)
        while True:
            try:
                message = next(gen)
            except StopIteration as stop:
                return str(stop.value or "")
            if on_progress is not None and message:
                on_progress(str(message))
    return fn(args)


def execute_tool(
    name: str,
    args: dict[str, Any],
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Run a tool through its full contract: permit -> validate -> run -> bound.

    Always returns a string (denials, validation rejections and errors included)
    so the model can read the outcome and recover rather than the loop crashing.
    """
    tool = _REGISTRY.get(name)
    if tool is None:
        # Unknown tool names are rejected here to keep the call boundary explicit.
        return f"未知工具: {name}"
    denial = check_permission(tool, args)
    if denial:
        return f"[未授权] {denial}"
    try:
        if tool.validate is not None:
            rejected = tool.validate(args)
            if rejected:
                return f"[未执行] {rejected}"
        result = invoke_tool(tool, args, on_progress)
    except Exception as exc:  # noqa: BLE001 — surface failures to the model, don't crash the loop
        return f"工具 {name} 执行出错: {type(exc).__name__}: {exc}"
    if isinstance(result, str) and len(result) > tool.max_result_chars:
        result = result[: tool.max_result_chars] + " …(结果过长已截断,请用更具体的参数缩小检索范围)"
    return result
