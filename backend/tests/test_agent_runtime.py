"""Tests for the selectable agent runtime boundary."""

from __future__ import annotations

import pytest

from backend.app.agent import langgraph_runtime, runtime


@pytest.fixture(autouse=True)
def _clear_runtime_env(monkeypatch):
    monkeypatch.delenv("SCISCOPE_AGENT_RUNTIME", raising=False)


def test_default_runtime_is_langgraph(monkeypatch):
    class _Runtime:
        @staticmethod
        def stream_agent(question, history=None, model=None):
            return iter([("final", f"graph:{question}")])

    monkeypatch.setattr(
        runtime,
        "_langgraph_runtime",
        lambda: _Runtime,
    )

    events = list(runtime.stream_agent("hello"))

    assert runtime.selected_runtime_name() == "langgraph"
    assert events == [("final", "graph:hello")]


def test_legacy_runtime_still_available_as_fallback(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "legacy")
    monkeypatch.setattr(
        runtime.legacy_loop,
        "stream_agent",
        lambda question, history=None, model=None: iter([("final", f"legacy:{question}")]),
    )

    events = list(runtime.stream_agent("hello"))

    assert runtime.selected_runtime_name() == "legacy"
    assert events == [("final", "legacy:hello")]


def test_langgraph_runtime_wraps_legacy_events(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "langgraph")
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_needs_plan", lambda question: True)
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_make_plan", lambda question, model: ["search evidence"])
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_self_critique", lambda *args: None)
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_run_tools", lambda tool_calls, executed: ["ok"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        if any(message.get("role") == "tool" for message in messages):
            return "grounded answer", []
        return (
            "",
            [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "search_literature", "arguments": '{"query": "rag"}'},
                }
            ],
        )

    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_stream_chat", fake_stream_chat)

    events = list(runtime.stream_agent("rag"))
    result = runtime.run_agent("rag")

    assert runtime.selected_runtime_name() == "langgraph"
    assert events[:3] == [
        ("plan", ["search evidence"]),
        ("tool_call", {"name": "search_literature", "args": {"query": "rag"}}),
        ("tool_result", {"name": "search_literature", "result": "ok"}),
    ]
    assert events[-1] == ("final", "grounded answer")
    assert result["answer"] == "grounded answer"
    assert result["steps"] == 1
    assert result["tools_used"] == [{"name": "search_literature", "args": {"query": "rag"}}]
    assert result["runtime"] == "langgraph"


def test_langgraph_runtime_reflects_and_retries_weak_answer(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "langgraph")
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_needs_plan", lambda question: False)
    answers = iter(["没有找到相关信息", "改进后的证据回答"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        return next(answers), []

    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_stream_chat", fake_stream_chat)

    events = list(runtime.stream_agent("请分析RAG研究现状"))

    assert ("reflect", "你没有调用任何工具就回答了。请先用 search_literature 等工具检索证据,再据实回答。") in events
    assert events[-1] == ("final", "改进后的证据回答")


def test_unknown_runtime_fails_fast(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "crew")

    with pytest.raises(ValueError, match="Unsupported SCISCOPE_AGENT_RUNTIME"):
        runtime.selected_runtime_name()
