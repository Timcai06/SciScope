"""Tests for the PreToolUse / PostToolUse tool lifecycle hooks.

The hook registry is module-global, so the autouse fixture clears it around every
test — both to isolate cases and to guarantee no hook leaks into the rest of the
suite (native tool behaviour must stay unchanged when no hooks are registered).
"""

from __future__ import annotations

import pytest

from backend.app.agent import tools
from backend.app.agent.tools import base


@pytest.fixture(autouse=True)
def _clear_hooks():
    tools.clear_hooks()
    yield
    tools.clear_hooks()


@pytest.fixture
def echo_tool(monkeypatch):
    tool = base.Tool(name="t_echo", schema={}, run=lambda a: "RESULT")
    monkeypatch.setitem(base._REGISTRY, tool.name, tool)
    return tool


def test_no_hooks_leaves_result_unchanged(echo_tool):
    assert tools.execute_tool("t_echo", {}) == "RESULT"


def test_pre_hook_deny_blocks_execution(monkeypatch):
    ran: list[int] = []
    tool = base.Tool(name="t_block", schema={}, run=lambda a: (ran.append(1), "RAN")[1])
    monkeypatch.setitem(base._REGISTRY, tool.name, tool)
    tools.register_hook("PreToolUse", lambda ctx: tools.HookResult(decision="deny", reason="政策不允许"))

    out = tools.execute_tool("t_block", {})
    assert out == "[未授权] 政策不允许"
    assert ran == []  # the tool never ran


def test_pre_hook_context_is_prepended(echo_tool):
    tools.register_hook("PreToolUse", lambda ctx: tools.HookResult(additional_context="[上下文]"))
    assert tools.execute_tool("t_echo", {}) == "[上下文]\nRESULT"


def test_post_hook_context_is_appended(echo_tool):
    tools.register_hook("PostToolUse", lambda ctx: tools.HookResult(additional_context="(已审计)"))
    assert tools.execute_tool("t_echo", {}) == "RESULT\n(已审计)"


def test_post_hook_receives_name_args_and_result(echo_tool):
    seen: dict = {}

    def hook(ctx):
        seen.update(event=ctx.event, name=ctx.name, args=ctx.args, result=ctx.result)
        return None

    tools.register_hook("PostToolUse", hook)
    tools.execute_tool("t_echo", {"x": 1})
    assert seen == {"event": "PostToolUse", "name": "t_echo", "args": {"x": 1}, "result": "RESULT"}


def test_multiple_post_hooks_run_in_registration_order(echo_tool):
    tools.register_hook("PostToolUse", lambda ctx: tools.HookResult(additional_context="A"))
    tools.register_hook("PostToolUse", lambda ctx: tools.HookResult(additional_context="B"))
    assert tools.execute_tool("t_echo", {}) == "RESULT\nA\nB"


def test_clear_hooks_restores_native_behaviour(echo_tool):
    tools.register_hook("PostToolUse", lambda ctx: tools.HookResult(additional_context="X"))
    tools.clear_hooks()
    assert tools.execute_tool("t_echo", {}) == "RESULT"


def test_allow_hook_does_not_bypass_validate(monkeypatch):
    tool = base.Tool(
        name="t_val", schema={}, run=lambda a: "OK",
        validate=lambda a: None if a.get("id") else "请提供 id",
    )
    monkeypatch.setitem(base._REGISTRY, tool.name, tool)
    tools.register_hook("PreToolUse", lambda ctx: tools.HookResult(decision="allow"))
    assert tools.execute_tool("t_val", {}).startswith("[未执行]")
    assert tools.execute_tool("t_val", {"id": "W123"}) == "OK"
