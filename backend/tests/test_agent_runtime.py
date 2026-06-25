"""Tests for the selectable agent runtime boundary."""

from __future__ import annotations

import pytest

from backend.app.agent import langgraph_runtime, runtime


@pytest.fixture(autouse=True)
def _clear_runtime_env(monkeypatch):
    monkeypatch.delenv("SCISCOPE_AGENT_RUNTIME", raising=False)


def test_default_runtime_is_legacy(monkeypatch):
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
    monkeypatch.setattr(
        langgraph_runtime.legacy_loop,
        "stream_agent",
        lambda question, history=None, model=None: iter(
            [
                ("plan", ["search evidence"]),
                ("tool_call", {"name": "search_literature", "args": {"query": question}}),
                ("tool_result", {"name": "search_literature", "result": "ok"}),
                ("final", "grounded answer"),
            ]
        ),
    )
    monkeypatch.setattr(langgraph_runtime.legacy_loop, "_detect_model", lambda: "test-model")

    events = list(runtime.stream_agent("rag"))
    result = runtime.run_agent("rag")

    assert runtime.selected_runtime_name() == "langgraph"
    assert events[-1] == ("final", "grounded answer")
    assert result["answer"] == "grounded answer"
    assert result["steps"] == 1
    assert result["tools_used"] == [{"name": "search_literature", "args": {"query": "rag"}}]
    assert result["runtime"] == "langgraph"


def test_unknown_runtime_fails_fast(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_RUNTIME", "crew")

    with pytest.raises(ValueError, match="Unsupported SCISCOPE_AGENT_RUNTIME"):
        runtime.selected_runtime_name()
