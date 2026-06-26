"""Tool contract + pre-execution validation gate."""

from __future__ import annotations

from backend.app.agent import tools
from backend.app.agent.tools import execute_tool, is_read_only


def test_registry_covers_every_schema():
    schema_names = {s["function"]["name"] for s in tools.TOOL_SCHEMAS}
    assert schema_names == set(tools._REGISTRY)
    assert len(tools.TOOLS) == len(schema_names)


def test_all_current_tools_are_read_only():
    assert all(t.is_read_only for t in tools.TOOLS)
    assert is_read_only("search_literature") is True
    assert is_read_only("nonexistent") is True  # safe default


def test_validate_paper_id_accepts_real_looking_ids():
    assert tools._validate_paper_id("W4411065983") is None
    assert tools._validate_paper_id("arXiv:2305.12345") is None
    assert tools._validate_paper_id("10.1145/3292500") is None


def test_validate_paper_id_rejects_fabrications():
    assert tools._validate_paper_id("machine learning")  # topic phrase (space)
    assert tools._validate_paper_id("00000001")  # zero-padded placeholder
    assert tools._validate_paper_id("0")
    assert tools._validate_paper_id("")  # empty
    assert tools._validate_paper_id("paper_id")  # placeholder word


def test_execute_tool_blocks_fabricated_id_before_running():
    # A topic phrase passed as paper_id is rejected by the gate — no DB hit.
    out = execute_tool("recommend_papers", {"paper_id": "machine learning"})
    assert out.startswith("[未执行]")
    assert "search_literature" in out


def test_execute_tool_blocks_zero_padded_id():
    out = execute_tool("get_paper", {"paper_id": "00000001"})
    assert out.startswith("[未执行]")


def test_compare_papers_validates_both_ids():
    out = execute_tool("compare_papers", {"paper_id_a": "valid_id", "paper_id_b": "topic phrase"})
    assert out.startswith("[未执行]")
    assert "paper_id_b" in out


def test_export_bibliography_rejects_empty_and_fabricated():
    assert execute_tool("export_bibliography", {"paper_ids": []}).startswith("[未执行]")
    assert execute_tool("export_bibliography", {"paper_ids": ["00000001"]}).startswith("[未执行]")


def test_unknown_tool_is_rejected():
    assert execute_tool("does_not_exist", {}) == "未知工具: does_not_exist"
