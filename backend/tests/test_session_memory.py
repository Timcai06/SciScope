"""Tests for the session memory service (the agent memory dir is isolated to a
tmp path by the autouse fixture in conftest.py)."""

from __future__ import annotations

from backend.app.agent import session_memory as M


def test_recall_empty_for_new_or_missing_session():
    assert M.recall(None) == []
    assert M.recall("brand-new") == []
    assert M.recall_prompt("brand-new") == ""


def test_remember_then_recall_roundtrips_and_dedupes():
    M.remember("s1", "研究关注: 图神经网络")
    M.remember("s1", "研究关注: 图神经网络")  # duplicate ignored
    M.remember("s1", "偏好: 中文综述")
    assert M.recall("s1") == ["研究关注: 图神经网络", "偏好: 中文综述"]


def test_remember_is_noop_without_session_or_facts():
    assert M.remember(None, "x") == []
    assert M.remember("s2", "   ") == []
    assert M.recall("s2") == []


def test_recall_prompt_formats_memories():
    M.remember("s3", "研究关注: RAG", "曾问: 检索增强")
    prompt = M.recall_prompt("s3")
    assert prompt.startswith("已知该用户")
    assert "- 研究关注: RAG" in prompt and "- 曾问: 检索增强" in prompt


def test_memory_is_capped():
    for i in range(M.MAX_MEMORIES + 5):
        M.remember("s4", f"fact-{i}")
    stored = M.recall("s4")
    assert len(stored) == M.MAX_MEMORIES
    assert stored[-1] == f"fact-{M.MAX_MEMORIES + 4}"  # newest kept
    assert "fact-0" not in stored  # oldest dropped


def test_extract_and_remember_uses_injected_summarizer():
    seen = {}

    def fake_summarize(question, answer):
        seen.update(q=question, a=answer)
        return "- 关注图神经网络的可解释性\n- 偏好近三年文献"

    facts = M.extract_and_remember("s5", "GNN 可解释性有哪些方法", "……", fake_summarize)
    assert seen == {"q": "GNN 可解释性有哪些方法", "a": "……"}
    assert facts == ["关注图神经网络的可解释性", "偏好近三年文献"]
    assert M.recall("s5") == facts


def test_extract_and_remember_noop_without_session():
    assert M.extract_and_remember(None, "q", "a", lambda q, a: "x") == []
