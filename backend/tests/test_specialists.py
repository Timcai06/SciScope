"""Specialist sub-agents + delegate tool (multi-agent, direction ③)."""

from __future__ import annotations

from backend.app.agent import specialists
from backend.app.agent.tools import execute_tool


def test_unknown_role_is_reported():
    assert "未知专员角色" in specialists.run_specialist("nope", "task")


def test_empty_task_is_reported(monkeypatch):
    monkeypatch.setattr(specialists, "detect_model", lambda: "m")
    assert "任务为空" in specialists.run_specialist("reviewer", "  ")


def test_no_specialist_can_delegate():
    # Structural recursion guard: specialists never get the delegate tool.
    for spec in specialists.SPECIALISTS.values():
        assert "delegate" not in spec["tools"]


def test_specialist_runs_bounded_tool_loop(monkeypatch):
    monkeypatch.setattr(specialists, "detect_model", lambda: "test-model")
    steps = iter([
        ("", [{"id": "c1", "type": "function", "function": {"name": "search_literature", "arguments": '{"query":"rag"}'}}]),
        ("综述结论:RAG 现状…", []),
    ])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield
        return next(steps)

    monkeypatch.setattr(specialists, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(specialists, "run_tools", lambda tool_calls, executed: ["evidence"])

    out = specialists.run_specialist("reviewer", "综述 RAG")
    assert out == "综述结论:RAG 现状…"


def test_delegate_tool_dispatches_to_specialist(monkeypatch):
    monkeypatch.setattr(specialists, "run_specialist", lambda role, task: f"[{role}] {task}")
    assert execute_tool("delegate", {"role": "reviewer", "task": "综述 X"}) == "[reviewer] 综述 X"
