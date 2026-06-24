"""Tests for the agentic loop's planning + reflection + retrieval contract.

LLM-dependent paths are exercised by monkeypatching the single completion helper,
so these stay hermetic (no live LLM, no DB).
"""

import pytest

from backend.app.agent import loop
from backend.app.services import evidence_chat, retrieval_service
from data_pipeline.loaders import load_papers
from data_pipeline.sample_data import sample_papers_path


@pytest.fixture(autouse=True)
def _clear_db_env(monkeypatch):
    monkeypatch.delenv("SCISCOPE_DB_DSN", raising=False)
    monkeypatch.delenv("SCISCOPE_DATABASE_URL", raising=False)


def test_parse_plan_strips_bullets_and_caps():
    raw = "步骤:\n1. 检索 RAG 论文\n- 检索 GAN 论文\n3) 对比两者\n\n4、综合作答\n5. 多余步骤"
    steps = loop._parse_plan(raw)
    assert steps == ["检索 RAG 论文", "检索 GAN 论文", "对比两者", "综合作答"]  # header dropped, capped at 4


def test_needs_plan_heuristic():
    assert loop._needs_plan("对比扩散模型和GAN") is True       # comparison marker
    assert loop._needs_plan("推荐几篇关于RAG的论文") is True     # recommend marker
    assert loop._needs_plan("什么是RAG") is False               # short simple lookup
    assert loop._needs_plan("你好") is False                    # greeting / meta
    assert loop._needs_plan("帮我梳理一下知识图谱在生物医学中的研究现状") is True


def test_self_critique_returns_none_on_ok(monkeypatch):
    monkeypatch.setattr(loop, "_complete", lambda messages, model: "OK")
    assert loop._self_critique("q", "a grounded answer", "m") is None


def test_self_critique_returns_reason_on_retry(monkeypatch):
    monkeypatch.setattr(loop, "_complete", lambda messages, model: "RETRY: 缺少对方法细节的检索")
    reason = loop._self_critique("q", "weak answer", "m")
    assert reason == "缺少对方法细节的检索"


def test_run_tools_dedups_identical_repeats(monkeypatch):
    """An identical (name, args) repeat is short-circuited, not re-executed."""
    calls = []
    monkeypatch.setattr(loop, "execute_tool",
                        lambda name, args: calls.append((name, args)) or f"ran {name}")
    executed: dict = {}
    tc = {"function": {"name": "get_trends", "arguments": '{"keyword": "rag"}'}}

    first = loop._run_tools([tc], executed)
    repeat = loop._run_tools([tc], executed)

    assert first == ["ran get_trends"]
    assert repeat == [loop._REPEAT_NOTE]
    assert len(calls) == 1  # executed exactly once despite two identical calls


class _FixedProvider:
    def complete(self, prompt: str) -> str:
        return "RAG improves generation with retrieved evidence [1]."


def test_retrieval_memory_contract_ignores_live_db(monkeypatch):
    """retrieval='memory' must use the sample papers even if a DB looks available."""
    monkeypatch.setattr(retrieval_service, "is_available", lambda: True)  # pretend DB is up
    monkeypatch.setattr(evidence_chat, "_semantic_support", lambda *a, **k: None)  # skip embedder
    papers = load_papers(sample_papers_path())

    response = evidence_chat.answer_question(
        "rag", papers, provider=_FixedProvider(), retrieval="memory"
    )

    titles = {e.title for e in response.evidence}
    assert "Retrieval Augmented Generation for Scientific Question Answering" in titles
