"""Tests for the selectable agent runtime boundary."""

from __future__ import annotations

import pytest

from backend.app.agent import langgraph_runtime, runtime
from backend.app.agent.events import event_parts


@pytest.fixture(autouse=True)
def _clear_runtime_env(monkeypatch):
    monkeypatch.delenv("SCISCOPE_AGENT_RUNTIME", raising=False)


def test_default_runtime_is_langgraph(monkeypatch):
    class _Runtime:
        @staticmethod
        def stream_agent(question, history=None, model=None, session_id=None, retry=False):
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
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: True)
    monkeypatch.setattr(langgraph_runtime, "make_plan", lambda question, model: ["search evidence"])
    monkeypatch.setattr(langgraph_runtime, "self_critique", lambda *args: None)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed: ["ok"])

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

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    events = list(runtime.stream_agent("rag", session_id="s-1"))
    result = runtime.run_agent("rag", session_id="s-1")
    parts = [event_parts(event) for event in events]

    assert runtime.selected_runtime_name() == "langgraph"
    assert [(kind, payload) for kind, payload, _ in parts[:3]] == [
        ("plan", ["search evidence"]),
        ("tool_call", {"name": "search_literature", "args": {"query": "rag"}}),
        ("tool_result", {"name": "search_literature", "result": "ok"}),
    ]
    assert parts[1][2]["runtime"] == "langgraph"
    assert parts[1][2]["node"] == "execute_tools"
    assert parts[1][2]["session_id"] == "s-1"
    assert isinstance(parts[1][2]["elapsed_ms"], int)
    assert (parts[-1][0], parts[-1][1]) == ("final", "grounded answer")
    assert result["answer"] == "grounded answer"
    assert result["steps"] == 1
    assert result["tools_used"] == [{"name": "search_literature", "args": {"query": "rag"}}]
    assert result["runtime"] == "langgraph"
    assert result["session_id"] == "s-1"
    assert result["retry"] is False


def test_langgraph_runtime_marks_retry_requests(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "langgraph")
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        assert any("/retry 请求" in message.get("content", "") for message in messages)
        return "retry answer", []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    events = list(runtime.stream_agent("rag", session_id="s-retry", retry=True))
    parts = [event_parts(event) for event in events]
    result = runtime.run_agent("rag", session_id="s-retry", retry=True)

    assert parts[-1][0:2] == ("final", "retry answer")
    assert parts[-1][2]["retry"] is True
    assert parts[-1][2]["session_id"] == "s-retry"
    assert result["retry"] is True


def test_langgraph_runtime_reflects_and_retries_weak_answer(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "langgraph")
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    answers = iter(["没有找到相关信息", "改进后的证据回答"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        return next(answers), []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    events = list(runtime.stream_agent("请分析RAG研究现状"))

    parts = [event_parts(event) for event in events]

    assert ("reflect", "你没有调用任何工具就回答了。请先用 search_literature 等工具检索证据,再据实回答。") in [
        (kind, payload) for kind, payload, _ in parts
    ]
    assert (parts[-1][0], parts[-1][1]) == ("final", "改进后的证据回答")


def test_unknown_runtime_fails_fast(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "crew")

    with pytest.raises(ValueError, match="Unsupported SCISCOPE_AGENT_RUNTIME"):
        runtime.selected_runtime_name()
