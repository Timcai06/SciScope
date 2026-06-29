"""Tests for missing-tool-result self-healing (Claude Code yieldMissingToolResultBlocks)."""

from __future__ import annotations

from backend.app.agent.tool_runner import MISSING_RESULT_NOTE, repair_missing_tool_results


def _assistant(*ids):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": i, "type": "function", "function": {"name": "search_literature", "arguments": "{}"}} for i in ids
    ]}


def test_noop_when_all_tool_calls_answered():
    messages = [
        {"role": "user", "content": "q"},
        _assistant("a", "b"),
        {"role": "tool", "tool_call_id": "a", "content": "ra"},
        {"role": "tool", "tool_call_id": "b", "content": "rb"},
    ]
    assert repair_missing_tool_results(messages) == 0
    assert len(messages) == 4


def test_fills_all_missing_results():
    messages = [_assistant("a", "b")]  # assistant tool_calls with no tool replies at all
    assert repair_missing_tool_results(messages) == 2
    assert [m["role"] for m in messages] == ["assistant", "tool", "tool"]
    assert messages[1]["tool_call_id"] == "a" and messages[1]["content"] == MISSING_RESULT_NOTE
    assert messages[2]["tool_call_id"] == "b"


def test_fills_only_the_missing_one_and_keeps_adjacency():
    messages = [
        _assistant("a", "b"),
        {"role": "tool", "tool_call_id": "a", "content": "ra"},  # only a answered
        {"role": "user", "content": "next"},
    ]
    assert repair_missing_tool_results(messages) == 1
    # synthetic result for b is inserted right after a's result, before the user turn
    assert [m["role"] for m in messages] == ["assistant", "tool", "tool", "user"]
    assert messages[2]["tool_call_id"] == "b" and messages[2]["content"] == MISSING_RESULT_NOTE
    assert messages[3]["role"] == "user"


def test_ignores_assistant_without_tool_calls():
    messages = [{"role": "assistant", "content": "plain answer"}]
    assert repair_missing_tool_results(messages) == 0
    assert len(messages) == 1


def test_falls_back_to_function_name_when_id_missing():
    messages = [{"role": "assistant", "content": "", "tool_calls": [
        {"type": "function", "function": {"name": "get_trends", "arguments": "{}"}}
    ]}]
    assert repair_missing_tool_results(messages) == 1
    assert messages[1]["tool_call_id"] == "get_trends"
