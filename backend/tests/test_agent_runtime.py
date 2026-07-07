"""Tests for the LangGraph agent runtime and its public entrypoint."""

from __future__ import annotations

from backend.app.agent import langgraph_runtime, runtime
from backend.app.agent.events import event_parts
from backend.app.agent.llm import SYSTEM_PROMPT, build_system_prompt
from backend.app.agent.reflection import reflect_reason
from backend.app.agent.skills import list_skill_summaries, skills_prompt
from backend.app.agent.tools import _REGISTRY


def test_reflect_does_not_force_tools_for_common_sense_question():
    # No literature intent + tool-free answer -> let it stand, no retry.
    assert reflect_reason("机器学习是让计算机从数据中学习的方法。", 0, "什么是机器学习?") is None


def test_reflect_does_not_force_tools_for_capability_boundary_question():
    answer = "除了科研文献分析,我还能帮助你解释概念、整理写作结构、规划复现步骤,但不能替代通用联网搜索。"
    assert reflect_reason(answer, 0, "除了科研文献,你还会什么?") is None


def test_reflect_still_forces_tools_for_exceptive_literature_question():
    reason = reflect_reason("还有知识图谱和重排序等方法。", 0, "除了RAG,最近文献里还有哪些检索增强方法?")
    assert reason is not None and "search_literature" in reason


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


def test_system_prompt_carries_date_and_corpus_time_boundary():
    # The model must know today's date and the corpus snapshot boundary to
    # calibrate "最新/近年" questions instead of guessing coverage.
    from datetime import date

    from src.analysis.data_readiness import RECENT_YEAR_END

    prompt = build_system_prompt()
    assert date.today().isoformat() in prompt
    assert f"收录至 {RECENT_YEAR_END} 年" in prompt


def test_system_prompt_enforces_citations_and_conclusion_first():
    # Evidence grounding is the product moat: key claims must carry a traceable
    # source, answers must lead with the conclusion, and reporting must be honest
    # both ways (no forced verdicts, no needless hedging).
    assert "标注出处" in SYSTEM_PROMPT
    assert "结论先行" in SYSTEM_PROMPT
    assert "不要硬撑出确定结论" in SYSTEM_PROMPT
    assert "不要堆砌多余的免责声明" in SYSTEM_PROMPT


def test_system_prompt_caps_length_and_bans_closing_recap():
    # Pinned from the experience run: complex answers ran 800-2100 chars, padded
    # by a closing 小结 section restating the whole answer.
    assert "小标题至多 3 个" in SYSTEM_PROMPT
    assert "不要再加「小结/总结」段" in SYSTEM_PROMPT


def test_system_prompt_bans_narration_and_demands_faithful_directions():
    # Pinned from the 2026-07 experience run: transition narration leaked into
    # final answers, a vague question triggered blind searching, and a falling
    # trend was reported as growth.
    assert "过渡旁白" in SYSTEM_PROMPT
    assert "反问澄清" in SYSTEM_PROMPT
    assert "不得说反" in SYSTEM_PROMPT


def test_make_plan_receives_previous_answer_for_reference_resolution(monkeypatch):
    # 「你刚才提到的第 2 篇论文」can only be planned correctly if the planner sees
    # the previous answer; without it the plan fabricated get_paper(paper_id="2").
    from backend.app.agent import planning

    captured: dict = {}

    def fake_complete(messages, model):
        captured["prompt"] = messages[-1]["content"]
        return "用 search_literature 按标题检索 HopRAG"

    monkeypatch.setattr(planning, "complete", fake_complete)
    steps = planning.make_plan("第 2 篇论文讲了什么?", "test-model", context="2. HopRAG (2025)")
    assert steps
    assert "HopRAG (2025)" in captured["prompt"]
    assert "不要编造 paper_id" in captured["prompt"]


def test_reflect_lets_grounded_honest_verdict_stand():
    # A cited answer concluding 证据不足 must NOT be retried into confirming the
    # claim (confirmation bias observed live on 2026-07-07: the critic pushed
    # 证据不足 into 明确支持, overriding verify_claim's stance verdict).
    answer = "现有文献对该论断证据不足:《LLM Risks》(2023) 仅描述风险,缺乏实证研究量化因果。"
    assert reflect_reason(answer, 2, "求证:大语言模型会加剧学术不端?") is None


def test_reflect_still_retries_uncited_weak_answer():
    # Without citations the weak-answer retry still applies.
    assert reflect_reason("抱歉,没有找到相关信息。", 1, "RAG 领域最新研究趋势如何?") is not None


def test_self_critique_must_not_demand_claim_confirmation(monkeypatch):
    from backend.app.agent import reflection

    captured: dict = {}

    def fake_complete(messages, model):
        captured["prompt"] = messages[-1]["content"]
        return "OK"

    monkeypatch.setattr(reflection, "complete", fake_complete)
    reflection.self_critique("求证: X 导致 Y", "证据不足", "test-model")
    assert "严禁因为回答没有证实用户的说法而要求重试" in captured["prompt"]


def test_self_critique_criteria_match_product_citation_format(monkeypatch):
    # The critic once demanded DOIs/journal issues the product never emits,
    # forcing pointless retries; the rubric must accept 标题+年份(+paper_id).
    from backend.app.agent import reflection

    captured: dict = {}

    def fake_complete(messages, model):
        captured["prompt"] = messages[-1]["content"]
        return "OK"

    monkeypatch.setattr(reflection, "complete", fake_complete)
    assert reflection.self_critique("问题", "回答", "test-model") is None
    assert "不要求 DOI" in captured["prompt"]


def test_system_prompt_is_sectioned_and_catalog_backed_by_registry():
    prompt = build_system_prompt()
    for section in (
        "# identity",
        "# context",
        "# capability_boundary",
        "# tool_policy",
        "# evidence_policy",
        "# answer_style",
        "# tone",
        "# skill_catalog",
        "# tool_catalog",
    ):
        assert section in prompt
    assert "search_literature" in prompt
    assert "verify_claim" in prompt
    assert "/claim-check" in prompt
    assert "/literature-review" in prompt
    assert "除了科研文献还能做什么" in prompt


def test_skill_catalog_is_backed_by_real_tools():
    summaries = list_skill_summaries()
    assert {skill.name for skill in summaries} >= {"claim-check", "literature-review", "trend-analysis"}
    assert "/claim-check" in skills_prompt()

    for skill in summaries:
        for tool in skill.tools:
            assert tool in _REGISTRY, f"{skill.name} declares missing tool {tool}"


def test_langgraph_runtime_streams_plan_tool_and_grounded_answer(monkeypatch):
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: True)
    monkeypatch.setattr(langgraph_runtime, "make_plan", lambda question, model, context="": ["search evidence"])
    monkeypatch.setattr(langgraph_runtime, "self_critique", lambda *args: None)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: ["ok"])

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


def test_langgraph_runtime_uses_fresh_system_prompt_builder(monkeypatch):
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "build_system_prompt", lambda: "fresh prompt from builder")

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        assert messages[0] == {"role": "system", "content": "fresh prompt from builder"}
        return "ok", []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    parts = [event_parts(event) for event in runtime.stream_agent("你好")]
    assert parts[-1][0:2] == ("final", "ok")


def test_skill_prompt_caps_tool_loop_and_forces_synthesis(monkeypatch):
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: ["trend evidence"] * len(tool_calls))

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        if tools is None:
            return "final from capped skill evidence", []
        return (
            "",
            [
                {
                    "id": "call-trend",
                    "type": "function",
                    "function": {"name": "get_trends", "arguments": '{"keyword": "rag"}'},
                }
            ],
        )

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    question = "你正在执行 SciScope 技能: 趋势分析。\n研究主题:\nrag"
    result = runtime.run_agent(question, session_id="skill-budget")

    assert result["steps"] == 2
    assert result["tools_used"] == [
        {"name": "get_trends", "args": {"keyword": "rag"}},
        {"name": "get_trends", "args": {"keyword": "rag"}},
    ]
    assert result["stop_reason"] == "tool_budget"
    assert result["answer"] == "final from capped skill evidence"


def test_agent_max_tool_calls_caps_runtime_tools(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_MAX_TOOL_CALLS", "1")
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: ["evidence"] * len(tool_calls))

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        if tools is None:
            return "final after capped runtime tools", []
        return (
            "",
            [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "search_literature", "arguments": '{"query": "rag"}'},
                },
                {
                    "id": "call-2",
                    "type": "function",
                    "function": {"name": "get_trends", "arguments": '{"keyword": "rag"}'},
                },
            ],
        )

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    result = runtime.run_agent("rag", session_id="global-tool-budget")

    assert result["tools_used"] == [{"name": "search_literature", "args": {"query": "rag"}}]
    assert result["stop_reason"] == "tool_budget"
    assert result["answer"] == "final after capped runtime tools"


def test_skill_prompt_forces_required_first_tool_when_model_skips(monkeypatch):
    monkeypatch.setattr(langgraph_runtime, "detect_model", lambda: "test-model")
    monkeypatch.setattr(langgraph_runtime, "needs_plan", lambda question: False)
    monkeypatch.setattr(langgraph_runtime, "run_tools", lambda tool_calls, executed, on_progress=None: ["claim evidence"])

    def fake_stream_chat(messages, model, tools):
        if False:
            yield ("text", "")
        if tools is None or any(message.get("role") == "tool" for message in messages):
            return "final after forced claim evidence", []
        return "model tried to answer without tools", []

    monkeypatch.setattr(langgraph_runtime, "stream_chat", fake_stream_chat)

    question = "你正在执行 SciScope 技能: 论断核查。\n\n输入论断:\nRAG 能降低大模型幻觉\n\n工作要求:\n- 第一动作必须调用 verify_claim"
    result = runtime.run_agent(question, session_id="skill-forced-tool")

    assert result["steps"] == 1
    assert result["tools_used"] == [{"name": "verify_claim", "args": {"claim": "RAG 能降低大模型幻觉"}}]
    assert result["answer"] == "final after forced claim evidence"


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


def test_stream_chat_uses_configured_agent_timeout(monkeypatch):
    monkeypatch.setenv("SCISCOPE_AGENT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    from backend.app.agent import llm

    seen = {}

    class FakeResponse:
        def __enter__(self):
            return iter([b"data: [DONE]\n"])

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)

    llm.drain(llm.stream_chat([], "deepseek-chat", None), lambda kind, payload: None)

    assert seen["timeout"] == 7


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
