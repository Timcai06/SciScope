"""LLM transport and shared prompt utilities for SciScope agent runtimes.

The system prompt is intentionally assembled from named sections instead of a
single prose blob. This keeps SciScope's capability boundary, evidence policy,
tool catalog, and answer style auditable as separate contracts.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator

from backend.app.agent.skills import skills_prompt
from backend.app.agent.tools import tools_prompt
from backend.app.core.config import get_settings


def _llm_target() -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model) for the generation backend.

    The model layer is pluggable: when ``SCISCOPE_LLM_PROVIDER=deepseek`` and a
    key is set, the agent generates via DeepSeek (OpenAI-compatible cloud) for far
    stronger output than the local 7B; otherwise it uses the local
    OpenAI-compatible endpoint (offline / air-gapped use). Both speak the same
    protocol — only the base URL and auth header differ.
    """
    s = get_settings()
    if s.llm_provider == "deepseek" and s.deepseek_api_key:
        return s.deepseek_base_url.rstrip("/"), s.deepseek_api_key, s.deepseek_model
    base = (s.local_llm_base_url or "http://127.0.0.1:8001/v1").rstrip("/")
    return base, (s.local_llm_api_key or ""), (s.local_llm_model or "")


def _is_cloud_provider() -> bool:
    s = get_settings()
    return s.llm_provider == "deepseek" and bool(s.deepseek_api_key)


@dataclass(frozen=True)
class PromptSection:
    """Named prompt block for auditability and focused tests."""

    name: str
    body: str


def _static_prompt_sections() -> tuple[PromptSection, ...]:
    return (
        PromptSection(
            "identity",
            "你是 SciScope 科研文献智能体,可访问一个 16 万篇科技文献的知识库。",
        ),
        PromptSection(
            "capability_boundary",
            (
                "先判断问题类型。涉及具体论文、研究现状、趋势、领域进展、文献数据、"
                "论文推荐、知识图谱或论断核查的问题,必须先用工具检索证据再回答。"
                "概念解释、方法原理、常识类通用问题,直接清晰、充分地作答即可,不必检索,"
                "也不要硬把它当成文献检索任务。"
                "用户询问你是谁、能做什么、除了科研文献还能做什么、系统边界或使用方法时,"
                "这是能力说明问题,应直接说明真实能力与限制,不要调用工具,"
                "也不要自责“没有调用工具”。"
            ),
        ),
        PromptSection(
            "tool_policy",
            (
                "对复杂问题先规划需要哪些检索步骤,再依次调用工具(可多步)。"
                "recommend_papers/get_paper/compare_papers 需要真实 paper_id——必须先用 "
                "search_literature 拿到,严禁编造 paper_id。"
                "检索要讲效率:通常 1-2 次检索拿到足够证据就停下作答,不要为同一问题"
                "反复换关键词搜很多遍;一次检索若无结果,至多再换一次关键词,仍无果就"
                "基于公认知识如实、完整地回答,并说明未在文献库中找到对应论文。"
                "同一工具同参数不要重复调用。"
            ),
        ),
        PromptSection(
            "evidence_policy",
            (
                "拿到工具结果后用中文综合归纳作答,只依据工具返回的真实数据,不编造,"
                "证据不足时如实说明。注意:检索结果里的「摘要片段」是论文摘要节选,"
                "「作者」才是作者。"
            ),
        ),
        PromptSection(
            "answer_style",
            (
                "回答格式要贴合问题本身,不要套固定模板:常识或简单问题就直接、简洁地回答"
                "(几句话即可,不必强行分层或加小标题);只有综述、对比、趋势这类复杂问题,"
                "才用小标题、短列表分层归纳。结构服务于问题,而不是每次都套同一个模具。"
                "综合归纳时不要默认按单篇论文逐篇复述,论文只能作为证据例子或出处补充,"
                "不要让答案围绕某一篇论文展开,除非用户明确要求分析单篇论文。"
                "当使用 get_trends 时,必须解释趋势本身、判断依据和推算含义,不要把动量、"
                "burst、Mann-Kendall、Sen's 斜率等内部指标名直接列成用户答案。"
                "涉及多步任务时,简要体现你如何选择工具、如何根据结果调整,"
                "但不要暴露冗长内部日志。"
            ),
        ),
        PromptSection(
            "tone",
            (
                "不要使用 emoji 表情符号(🍳🚀✅😀 之类);保持简洁克制的科研语气。"
                "需要轻量情绪点缀时,可偶尔使用颜文字(如 (・_・)、(๑•̀ㅂ•́)、(´・ω・`)),"
                "但每次回答至多一处,不要滥用。"
            ),
        ),
    )


def build_system_prompt() -> str:
    """Build the model-visible system prompt from current contracts.

    ``tools_prompt()`` is evaluated at call time so dynamically registered MCP
    tools and future capability plugins are reflected without editing this file.
    """
    sections = [*_static_prompt_sections()]
    skill_catalog = skills_prompt()
    if skill_catalog:
        sections.append(
            PromptSection(
                "skill_catalog",
                (
                    "可用专业工作流如下。它们只是任务展开方式,不是额外工具;"
                    "执行时仍必须使用 tool_catalog 中真实存在的工具。"
                    "当用户消息包含“你正在执行 SciScope 技能”时,必须先按该技能声明调用"
                    "至少一个真实工具,拿到工具结果后再作答;不要只根据模板或常识直接生成。"
                    "每个技能默认控制在 1-2 次工具调用内,除非用户明确要求扩展检索:\n" + skill_catalog
                ),
            )
        )
    sections.append(PromptSection("tool_catalog", "你可使用以下工具:\n" + tools_prompt()))
    return "\n\n".join(f"# {section.name}\n{section.body}" for section in sections)


# Backwards-compatible import surface for tests and older callers. The runtime
# calls build_system_prompt() per session so dynamic tool registration is fresh.
SYSTEM_PROMPT = build_system_prompt()


def detect_model() -> str | None:
    base, _key, model = _llm_target()
    if _is_cloud_provider():
        # DeepSeek is always reachable; trust the configured model (no probe).
        return model or "deepseek-chat"
    try:
        with urllib.request.urlopen(base + "/models", timeout=5) as resp:
            return json.loads(resp.read().decode())["data"][0]["id"]
    except Exception:
        return None


def stream_chat(messages: list[dict], model: str, tools: list | None) -> Iterator[tuple[str, Any]]:
    """Stream a chat completion and return ``(full_text, tool_calls)``."""
    base, key, _model = _llm_target()
    # Cloud models can write fuller answers; keep the local 7B lean for latency.
    max_tokens = 1500 if _is_cloud_provider() else 700
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True, "temperature": 0.1, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers=headers,
    )
    full_text = ""
    acc: dict[int, dict[str, Any]] = {}
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                full_text += delta["content"]
                yield ("text", delta["content"])
            for tool_call in delta.get("tool_calls") or []:
                idx = tool_call.get("index", 0)
                slot = acc.setdefault(idx, {"id": None, "name": None, "arguments": ""})
                if tool_call.get("id"):
                    slot["id"] = tool_call["id"]
                fn = tool_call.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    tool_calls = [
        {"id": slot["id"] or slot["name"], "type": "function", "function": {"name": slot["name"], "arguments": slot["arguments"]}}
        for slot in (acc[index] for index in sorted(acc))
        if slot["name"]
    ]
    return full_text, tool_calls


def drain(gen: Iterator[tuple[str, Any]], forward) -> tuple[str, list[dict]]:
    """Forward streamed text events and return a generator's final value."""
    while True:
        try:
            kind, payload = next(gen)
        except StopIteration as stop:
            return stop.value
        forward(kind, payload)


def complete(messages: list[dict], model: str) -> str:
    text, _ = drain(stream_chat(messages, model, None), lambda kind, payload: None)
    return text


def compact(messages: list[dict], budget_chars: int = 20000):
    """Cheap in-place context compaction (microcompact) — see compaction service.

    Backed by :mod:`backend.app.agent.compaction`: keeps the most recent tool
    results and clears older large ones. ``budget_chars`` is converted to a token
    budget (~4 chars/token) for backward compatibility. Returns the
    :class:`CompactionResult` so callers can surface telemetry (older callers that
    ignore the return value are unaffected).
    """
    from backend.app.agent.compaction import compact as _compact

    return _compact(messages, token_budget=max(budget_chars // 4, 1))
