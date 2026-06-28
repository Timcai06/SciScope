"""Tests for the two-tier context compaction service."""

from __future__ import annotations

from backend.app.agent import compaction as C
from backend.app.agent import langgraph_runtime as R


def test_maybe_autocompact_noop_under_budget():
    assert R._maybe_autocompact([{"role": "user", "content": "hi"}], "test-model") is None


def test_maybe_autocompact_noop_without_model():
    big = [{"role": "user", "content": "数" * 5000} for _ in range(6)]
    assert R._maybe_autocompact(big, None) is None


def test_maybe_autocompact_summarizes_over_budget(monkeypatch):
    monkeypatch.setattr(R, "_summarize_transcript", lambda transcript, model: "摘要")
    messages = [{"role": "system", "content": "S"}]
    messages += [{"role": "user", "content": "数" * 2000} for _ in range(7)]  # well over the 6000-token budget
    meta = R._maybe_autocompact(messages, "test-model")
    assert meta is not None
    assert meta["compaction"]["strategy"] == "autocompact"
    assert meta["compaction"]["messages_summarized"] >= 1
    assert meta["compaction"]["tokens_freed"] > 0


def test_estimate_tokens_cjk_vs_latin():
    assert C.estimate_tokens("") == 0
    # Same char count: CJK (~1.5 chars/token) is denser than latin (~4 chars/token).
    assert C.estimate_tokens("数据科学分析") > C.estimate_tokens("abcdef")


def test_microcompact_noop_under_budget():
    msgs = [{"role": "user", "content": "hi"}, {"role": "tool", "content": "x" * 100}]
    res = C.microcompact(msgs, token_budget=10_000)
    assert res.strategy == "none"
    assert msgs[1]["content"] == "x" * 100  # untouched
    assert res.tokens_freed == 0


def test_microcompact_clears_old_tool_results_keeps_recent():
    msgs = [
        {"role": "system", "content": "S"},
        {"role": "tool", "content": "A" * 2000},   # old → cleared
        {"role": "assistant", "content": "thinking"},
        {"role": "tool", "content": "B" * 2000},    # kept (within keep_recent)
        {"role": "tool", "content": "C" * 2000},    # kept (most recent)
    ]
    res = C.microcompact(msgs, token_budget=500, keep_recent=2)
    assert res.strategy == "microcompact"
    assert res.tool_results_cleared == 1
    assert C.CLEAR_NOTE in msgs[1]["content"] and len(msgs[1]["content"]) < 600
    assert msgs[3]["content"] == "B" * 2000  # recent kept in full
    assert msgs[4]["content"] == "C" * 2000
    assert res.tokens_after < res.tokens_before


def test_microcompact_leaves_short_results_alone():
    msgs = [{"role": "user", "content": "q" * 5000}, {"role": "tool", "content": "short"}]
    res = C.microcompact(msgs, token_budget=10, keep_recent=0)
    # nothing cleared (the only tool result is short), so strategy stays "none"
    assert res.tool_results_cleared == 0
    assert msgs[1]["content"] == "short"


def test_autocompact_summarizes_middle_keeps_system_and_recent():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "old q"},
        {"role": "assistant", "content": "old a"},
        {"role": "tool", "content": "old evidence " * 50},
        {"role": "user", "content": "recent q1"},
        {"role": "assistant", "content": "recent a1"},
        {"role": "user", "content": "recent q2"},
        {"role": "assistant", "content": "recent a2"},
    ]
    calls: list[str] = []

    def fake_summarize(transcript: str) -> str:
        calls.append(transcript)
        return "三句话摘要"

    res = C.autocompact(msgs, fake_summarize, token_budget=1, keep_recent_msgs=4)
    assert res.strategy == "autocompact"
    assert len(calls) == 1
    assert msgs[0] == {"role": "system", "content": "SYS"}            # system preserved
    assert msgs[1]["content"].startswith(C.SUMMARY_PREFIX)             # summary injected
    assert msgs[-1] == {"role": "assistant", "content": "recent a2"}   # recent preserved
    assert len(msgs) == 1 + 1 + 4                                      # sys + summary + recent
    assert res.messages_summarized == 3


def test_autocompact_noop_under_budget():
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "hi"}]
    res = C.autocompact(msgs, lambda t: "x", token_budget=10_000)
    assert res.strategy == "none"
    assert len(msgs) == 2


def test_compact_default_is_microcompact_in_place():
    msgs = [{"role": "tool", "content": "D" * 4000}, {"role": "tool", "content": "E" * 4000}]
    res = C.compact(msgs, token_budget=100, keep_recent=1)
    assert res.strategy == "microcompact"
    assert C.CLEAR_NOTE in msgs[0]["content"]   # oldest cleared
    assert msgs[1]["content"] == "E" * 4000     # most recent kept
