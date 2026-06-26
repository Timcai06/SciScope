"""Tests for the LangGraph agent runtime and its public entrypoint."""

from __future__ import annotations

from backend.app.agent import langgraph_runtime, runtime
from backend.app.agent.events import event_parts
from backend.app.agent.llm import SYSTEM_PROMPT
from backend.app.agent.reflection import reflect_reason


def test_reflect_does_not_force_tools_for_common_sense_question():
    # No literature intent + tool-free answer -> let it stand, no retry.
    assert reflect_reason("机器学习是让计算机从数据中学习的方法。", 0, "什么是机器学习?") is None


def test_reflect_pushes_tools_for_literature_question_without_tools():
    reason = reflect_reason("RAG 是一种检索增强方法。", 0, "RAG 领域最新研究趋势如何?")
    assert reason is not None and "search_literature" in reason


def test_runtime_entrypoint_delegates_to_langgraph():
    assert runtime.stream_agent is langgraph_runtime.stream_agent
    assert runtime.run_agent is langgraph_runtime.run_agent


def test_system_prompt_requires_synthesis_not_paper_by_paper():
    assert "不要默认按单篇论文逐篇复述" in SYSTEM_PROMPT
    assert "论文只能作为证据例子" in SYSTEM_PROMPT
    assert "不要把动量、burst、Mann-Kendall、Sen's 斜率等内部指标名直接列成用户答案" in SYSTEM_PROMPT


def test_langgraph_runtime_streams_plan_tool_and_grounded_answer(monkeypatch):
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

    assert [(kind, payload) for kind, payload, _ in parts[:3]] == [
        ("plan", ["search evidence"]),
        ("tool_call", {"name": "search_literature", "args": {"query": "rag"}}),
        ("tool_result", {"name": "search_literature", "result": "ok"}),
    ]
    assert parts[1][2]["runtime"] == "langgraph"
    assert parts[1][2]["node"] == "execute_tools"
    assert parts[1][2]["phase"] == "证据检索"
    assert parts[1][2]["session_id"] == "s-1"
    assert isinstance(parts[1][2]["elapsed_ms"], int)
    assert (parts[-1][0], parts[-1][1]) == ("final", "grounded answer")
    assert result["answer"] == "grounded answer"
    assert result["steps"] == 1
    assert result["tools_used"] == [{"name": "search_literature", "args": {"query": "rag"}}]
    assert result["runtime"] == "langgraph"
    assert result["session_id"] == "s-1"
    assert result["retry"] is False
    # stop_reason + token usage surfaced on the final event meta and the aggregate.
    assert parts[-1][2]["stop_reason"] == "completed"
    assert parts[-1][2]["tokens_in"] >= 0 and parts[-1][2]["tokens_out"] >= 0
    assert result["stop_reason"] == "completed"
    assert "tokens_out" in result


def test_langgraph_runtime_marks_retry_requests(monkeypatch):
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


def test_llm_routes_to_deepseek_when_keyed(monkeypatch):
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    from backend.app.agent import llm

    base, key, model = llm._llm_target()
    assert base == "https://api.deepseek.com"
    assert key == "sk-test"
    assert model == "deepseek-chat"
    # Cloud provider: detect_model trusts config, no network probe.
    assert llm.detect_model() == "deepseek-chat"


def test_llm_falls_back_to_local_without_key(monkeypatch):
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
    from backend.app.agent import llm

    base, key, _model = llm._llm_target()
    assert base == "http://127.0.0.1:8001/v1"
    assert key == ""
    assert llm._is_cloud_provider() is False


def test_langgraph_runtime_reflects_and_retries_weak_answer(monkeypatch):
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
