"""Tool lifecycle hooks — a Claude Code PreToolUse / PostToolUse analog.

A thin, registry-driven middleware layer around tool execution. Mirrors Claude
Code's hook model:

* **PreToolUse** hooks run before a tool executes. A hook may return a
  ``permissionDecision`` of ``deny``/``ask`` (blocking the call with a reason) or
  inject ``additional_context`` that is prepended to the result the model reads.
* **PostToolUse** hooks run after a tool returns. A hook may append
  ``additional_context`` (e.g. a citation reminder, a policy note, a metric tag).

The registry is **empty by default** — native behaviour is unchanged until a hook
is registered — so this is a pure extension point for cross-cutting concerns
(audit, metrics, policy, redaction) that the agent loop and individual tools never
have to know about. It generalises the built-in side-effect permission gate
(:func:`base.check_permission`) into a full, user-extensible lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

HookEvent = Literal["PreToolUse", "PostToolUse"]
PermissionDecision = Literal["allow", "deny", "ask"]


@dataclass(frozen=True)
class ToolHookContext:
    """What a hook is told about the tool call."""

    event: HookEvent
    name: str
    args: dict[str, Any]
    result: str | None = None  # only populated for PostToolUse


@dataclass(frozen=True)
class HookResult:
    """What a hook may return (all fields optional; ``None`` means "no opinion")."""

    # PreToolUse permission decision; "deny"/"ask" block the call.
    decision: PermissionDecision | None = None
    reason: str | None = None
    # Extra text surfaced to the model (Claude Code's additionalContext): prepended
    # for PreToolUse hooks, appended for PostToolUse hooks.
    additional_context: str | None = None


HookFn = Callable[[ToolHookContext], "HookResult | None"]

_HOOKS: dict[HookEvent, list[HookFn]] = {"PreToolUse": [], "PostToolUse": []}


def register_hook(event: HookEvent, fn: HookFn) -> None:
    """Register a hook for an event; hooks run in registration order."""
    _HOOKS[event].append(fn)


def clear_hooks(event: HookEvent | None = None) -> None:
    """Remove registered hooks (all events, or one). Mainly for tests/teardown."""
    for key in ([event] if event else list(_HOOKS)):
        _HOOKS[key].clear()


def pre_tool_use(name: str, args: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Run PreToolUse hooks.

    Returns ``(deny_reason, context_to_prepend)``: ``deny_reason`` is non-None when
    a hook blocks the call (first blocker wins); otherwise it is None and the
    second item is any additional context to prepend to the eventual result.
    """
    ctx = ToolHookContext("PreToolUse", name, args)
    extra: list[str] = []
    for fn in _HOOKS["PreToolUse"]:
        res = fn(ctx)
        if res is None:
            continue
        if res.decision in ("deny", "ask"):
            return (res.reason or f"PreToolUse 钩子阻断了 {name}", extra)
        if res.additional_context:
            extra.append(res.additional_context)
    return (None, extra)


def post_tool_use(name: str, args: dict[str, Any], result: str) -> str:
    """Run PostToolUse hooks; append any additional context to the result."""
    ctx = ToolHookContext("PostToolUse", name, args, result)
    extra: list[str] = []
    for fn in _HOOKS["PostToolUse"]:
        res = fn(ctx)
        if res is not None and res.additional_context:
            extra.append(res.additional_context)
    return result + "\n" + "\n".join(extra) if extra else result
