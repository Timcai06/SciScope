"""Tests for the slash-command / skill registry and its interception."""

from __future__ import annotations

from backend.app.agent import commands as C
from backend.app.agent import langgraph_runtime as R


def test_parse_command_splits_name_and_argument():
    assert C.parse_command("/review LLM safety") == ("review", "LLM safety")
    assert C.parse_command("  /Trend  graph nn ") == ("trend", "graph nn")
    assert C.parse_command("/") == ("help", "")
    assert C.parse_command("hello") is None
    assert C.parse_command("") is None


def test_is_command():
    assert C.is_command("/help")
    assert not C.is_command("how many papers in 2024")


def test_run_command_returns_none_for_plain_text():
    assert C.run_command("just a question") is None


def test_help_lists_registered_commands():
    out = C.run_command("/help")
    assert all(f"/{name}" in out for name in ("review", "trend", "verify", "search"))


def test_unknown_command_is_helpful_not_none():
    out = C.run_command("/nope")
    assert out is not None and "未知命令" in out


def test_command_without_argument_returns_usage(monkeypatch):
    called: list = []
    monkeypatch.setattr("backend.app.agent.specialists.run_specialist", lambda r, t: called.append((r, t)) or "X")
    out = C.run_command("/review")
    assert "用法" in out
    assert called == []  # the specialist is not invoked for an empty argument


def test_review_delegates_to_reviewer_specialist(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        "backend.app.agent.specialists.run_specialist",
        lambda role, task: seen.update(role=role, task=task) or "综述结果",
    )
    assert C.run_command("/review 图神经网络") == "综述结果"
    assert seen == {"role": "reviewer", "task": "图神经网络"}


def test_search_command_dispatches_to_tool(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        "backend.app.agent.tools.execute_tool",
        lambda name, args: seen.update(name=name, args=args) or "[]",
    )
    assert C.run_command("/search transformer") == "[]"
    assert seen == {"name": "search_literature", "args": {"query": "transformer"}}


def test_stream_agent_intercepts_command_without_llm():
    events = list(R.stream_agent("/help"))
    kinds = [e[0] for e in events]
    assert "plan" in kinds and "final" in kinds
    final = next(e for e in events if e[0] == "final")
    assert "/review" in final[1]                 # the help content
    assert final[2]["runtime"] == "command"      # meta marks the command path, not the LLM loop
