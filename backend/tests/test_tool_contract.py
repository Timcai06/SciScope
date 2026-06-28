"""Contract tests for the Claude-Code-style Tool abstraction.

These exercise the cross-cutting guarantees the agent loop relies on — schema
well-formedness, the side-effect/concurrency classification, the permission gate,
and the streaming-progress protocol — independently of any LLM or database.
"""

from __future__ import annotations

from backend.app.agent import tools
from backend.app.agent.tools import base


# --- A: self-contained tool modules / schema well-formedness ----------------
def test_every_native_tool_schema_is_wellformed():
    for tool in tools.NATIVE_TOOLS:
        fn = tool.schema["function"]
        assert tool.schema["type"] == "function"
        assert fn["name"] == tool.name, f"{tool.name}: schema name mismatch"
        params = fn["parameters"]
        assert params["type"] == "object"
        props = set(params.get("properties", {}))
        required = set(params.get("required", []))
        assert required <= props, f"{tool.name}: required {required - props} not in properties"
        assert tool.prompt_fragment, f"{tool.name}: missing prompt_fragment for the catalog"


def test_registry_schemas_and_tools_agree():
    schema_names = {s["function"]["name"] for s in tools.TOOL_SCHEMAS}
    assert schema_names == set(tools._REGISTRY)
    assert {t.name for t in tools.NATIVE_TOOLS} == schema_names


def test_paper_id_tools_have_validators():
    expect_validated = {"recommend_papers", "get_paper", "compare_papers", "export_bibliography"}
    for tool in tools.NATIVE_TOOLS:
        if tool.name in expect_validated:
            assert tool.validate is not None, f"{tool.name} should validate ids"
        else:
            assert tool.validate is None, f"{tool.name} should not validate"


# --- B: side-effect classification + permission gate ------------------------
def test_all_native_tools_are_read_only():
    assert all(t.side_effect == "read" for t in tools.NATIVE_TOOLS)
    assert all(t.is_read_only for t in tools.NATIVE_TOOLS)
    assert all(tools.is_read_only(t.name) for t in tools.NATIVE_TOOLS)


def test_permission_gate_blocks_write_tool_by_default():
    write_tool = base.Tool(name="t_write", schema={}, run=lambda a: "done", side_effect="write")
    assert base.ALLOW_WRITE_TOOLS is False
    assert base.check_permission(write_tool, {}) is not None  # denied


def test_permission_gate_allows_read_and_external():
    read_tool = base.Tool(name="t_read", schema={}, run=lambda a: "ok")
    external_tool = base.Tool(name="t_ext", schema={}, run=lambda a: "ok", side_effect="external")
    assert base.check_permission(read_tool, {}) is None
    assert base.check_permission(external_tool, {}) is None
    assert external_tool.is_read_only is False  # external runs sequentially


def test_per_tool_check_permissions_overrides_policy():
    gated = base.Tool(
        name="t_gated", schema={}, run=lambda a: "ok",
        check_permissions=lambda a: None if a.get("ok") else "需要 ok=true",
    )
    assert base.check_permission(gated, {"ok": True}) is None
    assert base.check_permission(gated, {}) == "需要 ok=true"


def test_execute_tool_denies_unauthorized_write(monkeypatch):
    write_tool = base.Tool(name="t_write2", schema={}, run=lambda a: "WROTE", side_effect="write")
    monkeypatch.setitem(base._REGISTRY, write_tool.name, write_tool)
    out = tools.execute_tool(write_tool.name, {})
    assert out.startswith("[未授权]")
    assert "WROTE" not in out


# --- D: streaming-progress protocol -----------------------------------------
def test_invoke_tool_streams_progress_and_returns_final():
    def streaming(args):
        yield "step 1"
        yield "step 2"
        return "FINAL"

    tool = base.Tool(name="t_stream", schema={}, run=streaming)
    seen: list[str] = []
    result = base.invoke_tool(tool, {}, on_progress=seen.append)
    assert seen == ["step 1", "step 2"]
    assert result == "FINAL"


def test_invoke_tool_handles_plain_handler():
    tool = base.Tool(name="t_plain", schema={}, run=lambda a: "VALUE")
    seen: list[str] = []
    assert base.invoke_tool(tool, {}, on_progress=seen.append) == "VALUE"
    assert seen == []  # no progress for a plain handler


def test_execute_tool_forwards_progress(monkeypatch):
    def streaming(args):
        yield "warming up"
        return "ANSWER"

    tool = base.Tool(name="t_stream2", schema={}, run=streaming)
    monkeypatch.setitem(base._REGISTRY, tool.name, tool)
    seen: list[str] = []
    result = tools.execute_tool(tool.name, {}, on_progress=seen.append)
    assert seen == ["warming up"]
    assert result == "ANSWER"
