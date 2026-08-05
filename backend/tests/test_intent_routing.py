"""A01 — deterministic intent routing: fixed test set, tool-call assertions,
clarification/no-tool degradation for vague & unknown questions."""

from __future__ import annotations

import pytest

from backend.app.agent import langgraph_runtime, runtime
from backend.app.agent.events import event_parts
from backend.app.agent.intents import classify_intent, routing_guidance


# --- Fixed test set: the three core intents + unknown + edge cases -------------
FIXED_SET: tuple[tuple[str, str], ...] = (
    # (question, expected intent name)
    ("有哪些关于图神经网络的论文?", "literature_search"),
    ("找一下 RAG 相关的文献", "literature_search"),
    ("帮我查最新的多模态大模型论文", "literature_search"),
    ("请综述一下联邦学习领域的研究现状", "field_review"),
    ("梳理一下知识图谱领域的发展进展", "field_review"),
    ("RAG 领域最近有哪些研究进展?", "field_review"),
    ("求证:大语言模型会加剧学术不端吗?", "claim_verification"),
    ("核查一下'多模态模型可用于医疗诊断'这个说法对不对", "claim_verification"),
    ("有没有证据支持'低碳饮食能减肥'?", "claim_verification"),
    ("图神经网络的研究趋势如何?", "trend_analysis"),
    ("对比 A 和 B 两篇论文", "paper_compare"),
    ("查询知识图谱中的研究社区", "graph_query"),
    ("推荐与这篇论文相似的论文", "paper_recommend"),
    ("什么是注意力机制?", "concept_explanation"),
    ("你是谁?", "meta_query"),
    ("除了科研文献,你还会什么?", "meta_query"),
    ("帮我看看", "vague_query"),
    ("。。。。。", "vague_query"),
    ("", "unknown"),
    ("量子纠缠的啤酒肚", "unknown"),  # plausible-looking but tool-less nonsense
)


@pytest.mark.parametrize(("question", "expected"), FIXED_SET)
def test_classify_intent_fixed_set(question: str, expected: str):
    assert classify_intent(question).name == expected


def test_classify_intent_skill_markers_win():
    assert classify_intent("你正在执行 SciScope 技能: 论断核查。\n输入论断:\nX 导致 Y").name == "skill_claim_check"
    assert classify_intent("你正在执行 SciScope 技能: 趋势分析。\n研究主题:\nrag").name == "skill_trend_analysis"


def test_intent_labels_are_user_facing_and_tools_are_real():
    from backend.app.agent.tools import get_tool

    for question, expected in FIXED_SET:
        intent = classify_intent(question)
        assert intent.label  # non-empty user-facing label
        if intent.primary_tool:
            assert get_tool(intent.primary_tool) is not None, f"{intent.name} -> {intent.primary_tool}"
        assert intent.reason  # classification basis is always present


# --- Intent event: observable on SSE, without leaking the steering prompt -----
def test_intent_event_emitted_without_guidance_leak(monkeypatch):
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        return "ok", []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    parts = [event_parts(e) for e in runtime.stream_agent("请综述 RAG 研究现状")]
    intent_events = [(kind, payload) for kind, payload, _ in parts if kind == "intent"]
    assert len(intent_events) == 1
    kind, payload = intent_events[0]
    assert kind == "intent"
    assert payload == {"intent": "field_review", "label": "领域综述", "reason": "命中关键词「综述」"}
    # The steering prompt itself must never ride the event stream.
    serialized = str(payload)
    assert "请优先调用" not in serialized
    assert "summarize_field" not in serialized


# --- Guidance injection --------------------------------------------------------
def test_routing_guidance_steers_primary_tool():
    g = routing_guidance(classify_intent("有哪些关于图神经网络的论文?"))
    assert "search_literature" in g
    g = routing_guidance(classify_intent("请综述一下联邦学习领域的研究现状"))
    assert "summarize_field" in g
    g = routing_guidance(classify_intent("图神经网络的研究趋势如何?"))
    assert "get_trends" in g


def test_claim_guidance_forbids_degrading_to_plain_search():
    g = routing_guidance(classify_intent("求证:大语言模型会加剧学术不端吗?"))
    assert "verify_claim" in g
    assert "不要把论断核查偷换成普通文献检索" in g


def test_vague_guidance_forbids_tools_and_asks_to_clarify():
    g = routing_guidance(classify_intent("帮我看看"))
    assert "不要调用任何工具" in g
    assert "反问澄清" in g
    assert "search_literature" not in g  # no tool steering for vague questions


def test_unknown_guidance_blocks_blind_search():
    g = routing_guidance(classify_intent("量子纠缠的啤酒肚"))
    assert "反问澄清" in g
    assert "不要盲目标发起检索" in g


def test_concept_and_meta_get_no_guidance():
    assert routing_guidance(classify_intent("什么是注意力机制?")) == ""
    assert routing_guidance(classify_intent("你是谁?")) == ""


# --- Tool-call assertions through the loop (mock LLM) -------------------------
def test_claim_question_forces_verify_claim_when_model_skips(monkeypatch):
    """A plain claim-check question must end up calling verify_claim even if the
    model tries to answer without tools (A01: 不能偷换为普通检索)."""
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: ["stance evidence"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        if tools is None or any(m.get("role") == "tool" for m in messages):
            return "核查结果:证据不足", []
        return "模型试图直接回答", []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    result = runtime.run_agent("求证:大语言模型会加剧学术不端吗?", session_id="a01-claim")
    assert result["tools_used"] == [{"name": "verify_claim", "args": {"claim": "大语言模型会加剧学术不端"}}]
    assert result["steps"] == 1


def test_claim_question_replaces_mistaken_search_with_verify_claim(monkeypatch):
    """REVISE regression: a claim-check question where the model misroutes to
    search_literature must be corrected to verify_claim, not silently degrade."""
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: ["stance evidence"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        if tools is None or any(m.get("role") == "tool" for m in messages):
            return "核查结果:证据不足", []
        return (
            "",
            [
                {
                    "id": "call-search",
                    "type": "function",
                    "function": {"name": "search_literature", "arguments": '{"query": "大语言模型 学术不端"}'},
                }
            ],
        )

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    result = runtime.run_agent("求证:大语言模型会加剧学术不端吗?", session_id="a01-misroute")
    assert result["tools_used"] == [{"name": "verify_claim", "args": {"claim": "大语言模型会加剧学术不端"}}]
    assert result["steps"] == 1


def test_claim_skill_replaces_mistaken_search_with_verify_claim(monkeypatch):
    """REVISE regression for the skill path: same replacement under skill_claim_check."""
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: ["stance evidence"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        if tools is None or any(m.get("role") == "tool" for m in messages):
            return "核查结果:证据不足", []
        return (
            "",
            [
                {
                    "id": "call-search",
                    "type": "function",
                    "function": {"name": "search_literature", "arguments": '{"query": "RAG 降低幻觉"}'},
                }
            ],
        )

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    question = "你正在执行 SciScope 技能: 论断核查。\n\n输入论断:\nRAG 能降低大模型幻觉\n\n工作要求:\n- 第一动作必须调用 verify_claim"
    result = runtime.run_agent(question, session_id="a01-skill-misroute")
    assert result["tools_used"] == [{"name": "verify_claim", "args": {"claim": "RAG 能降低大模型幻觉"}}]
    assert result["steps"] == 1


def test_claim_extraction_strips_shell_wording():
    assert langgraph_runtime._claim_from_question("求证:大语言模型会加剧学术不端吗?") == "大语言模型会加剧学术不端"
    assert langgraph_runtime._claim_from_question("核查一下'多模态模型可用于医疗诊断'这个说法对不对") == "多模态模型可用于医疗诊断"
    # Short questions still yield a clean claim.
    assert langgraph_runtime._claim_from_question("RAG 好吗?") == "RAG 好"


def test_vague_question_steers_clarification_not_search(monkeypatch):
    """vague intents get clarification guidance; the loop still lets the model
    produce the wording, and no tool is forced."""
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: [])

    captured: dict = {}

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        captured["system"] = " ".join(m.get("content", "") for m in messages if m.get("role") == "system")
        return "你想查哪方面的文献?我可以帮你检索、综述或核查论断。", []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    result = runtime.run_agent("帮我看看", session_id="a01-vague")
    assert result["steps"] == 0
    assert result["tools_used"] == []
    assert "不要调用任何工具" in captured["system"]
    assert "反问澄清" in captured["system"]


def test_literature_intent_guidance_reaches_the_model(monkeypatch):
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)

    captured: dict = {}

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        captured["system"] = " ".join(m.get("content", "") for m in messages if m.get("role") == "system")
        return "ok", []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)
    runtime.run_agent("有哪些关于图神经网络的论文?")
    assert "文献检索类问题" in captured["system"]
    assert "search_literature" in captured["system"]


# --- Degradation: no-tool answers still flow through reflect ------------------
def test_no_tool_answer_for_literature_intent_still_reflects(monkeypatch):
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    answers = iter(["直接说了个常识性回答", "改进后的证据回答"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        return next(answers), []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    events = list(runtime.stream_agent("有哪些关于图神经网络的论文?"))
    kinds = [kind for kind, _payload, _ in [event_parts(e) for e in events]]
    assert "reflect" in kinds  # degrade to the existing self-check, not a crash
    assert kinds[-1] == "final"


def test_llm_timeout_propagates_not_fake_success(monkeypatch):
    """A timed-out LLM call must surface as a failure (the API layer turns it
    into an ``error`` SSE frame), never as a silent success — intent routing
    must not swallow it."""
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)

    def boom(messages, model, tools):
        if False:
            yield ("text", "")
        raise TimeoutError("LLM timed out")

    monkeypatch.setattr(langgraph_runtime, "stream_chat", boom)

    with pytest.raises(TimeoutError):
        list(runtime.stream_agent("有哪些关于图神经网络的论文?"))
