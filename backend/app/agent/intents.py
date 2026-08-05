"""Deterministic intent routing for the SciScope agent loop (A01).

The agent loop stays LLM-driven for wording, but *intent* is classified
deterministically before the first LLM call so the loop can:

- expose which capability a question maps to (observable via an ``intent`` SSE
  event, without leaking the internal guidance text);
- steer the first tool choice for the three core research intents
  (找相关论文 / 总结领域 / 判定 claim 支持反驳) instead of hoping the model
  guesses the right tool;
- hard-force ``verify_claim`` when a claim-check question is asked and the model
  tries to answer without it (A01: 不能偷换为普通检索);
- constrain vague/unknown questions to clarification instead of blind searching.

Rules are keyword-priority lists, not a classifier model: deterministic,
unit-testable, and safe to run before any network/LLM call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentName = Literal[
    "skill_claim_check",
    "skill_trend_analysis",
    "skill_paper_recommend",
    "skill_literature_review",
    "claim_verification",
    "field_review",
    "trend_analysis",
    "paper_compare",
    "graph_query",
    "paper_recommend",
    "paper_detail",
    "literature_search",
    "concept_explanation",
    "meta_query",
    "vague_query",
    "unknown",
]

# Public intent labels — the only intent vocabulary exposed on SSE. They are
# user-facing capability names, not internal prompt fragments.
INTENT_LABELS: dict[IntentName, str] = {
    "skill_claim_check": "论断核查",
    "skill_trend_analysis": "趋势分析",
    "skill_paper_recommend": "论文推荐",
    "skill_literature_review": "领域综述",
    "claim_verification": "论断核查",
    "field_review": "领域综述",
    "trend_analysis": "趋势分析",
    "paper_compare": "论文对比",
    "graph_query": "图谱查询",
    "paper_recommend": "论文推荐",
    "paper_detail": "论文详情",
    "literature_search": "文献检索",
    "concept_explanation": "概念解释",
    "meta_query": "能力说明",
    "vague_query": "待澄清",
    "unknown": "未知",
}

# Preferred first tool per intent. None = no tool (answer directly / clarify).
INTENT_PRIMARY_TOOL: dict[IntentName, str | None] = {
    "skill_claim_check": "verify_claim",
    "skill_trend_analysis": "get_trends",
    "skill_paper_recommend": "search_literature",
    "skill_literature_review": "summarize_field",
    "claim_verification": "verify_claim",
    "field_review": "summarize_field",
    "trend_analysis": "get_trends",
    "paper_compare": "search_literature",
    "graph_query": "query_knowledge_graph",
    "paper_recommend": "search_literature",
    "paper_detail": "search_literature",
    "literature_search": "search_literature",
    "concept_explanation": None,
    "meta_query": None,
    "vague_query": None,
    "unknown": None,
}


@dataclass(frozen=True)
class Intent:
    name: IntentName
    label: str
    primary_tool: str | None
    reason: str  # short human-readable classification basis (SSE-safe)


# --- Classification rules (ordered by priority; first match wins) -------------

# Explicit SciScope skill prompts — same markers the runtime already recognizes.
_SKILL_MARKERS: tuple[tuple[IntentName, str], ...] = (
    ("skill_claim_check", "技能: 论断核查"),
    ("skill_trend_analysis", "技能: 趋势分析"),
    ("skill_paper_recommend", "技能: 论文推荐"),
    ("skill_literature_review", "技能: 文献综述"),
)

_CLAIM_MARKERS = (
    "求证", "核查", "对吗", "是否正确", "是不是真的", "有没有依据", "有没有证据",
    "是否有证据", "是否成立", "证据支持", "证据反驳", "验证一下", "查证",
    "是真的吗", "能否证实", "有没有道理", "立场", "真伪", "支持吗", "有依据吗",
    "verify", "evidence for", "is it true", "fact-check", "claim",
)

_REVIEW_MARKERS = (
    "综述", "研究现状", "研究进展", "领域进展", "领域发展", "概览", "梳理", "总结一下",
    "现状如何", "进展如何", "领域有哪些方向", "research landscape", "overview",
    "survey", "state of the art", "review",
)

_TREND_MARKERS = (
    "趋势", "演进", "演变", "发展脉络", "热度", "前景", "走向", "生命周期",
    "发展阶段", "trend", "evolution", "trajectory",
)

_COMPARE_MARKERS = (
    "对比", "比较", "区别", "差异", "异同", "相比", "vs", "versus", "compare",
)

_GRAPH_MARKERS = (
    "图谱", "社区", "作者网络", "合作关系", "共著", "知识图谱", "graph",
    "co-authorship", "collaboration network",
)

_RECOMMEND_MARKERS = (
    "推荐", "相似论文", "相关论文", "类似论文", "推荐文章", "recommend",
    "similar papers",
)

_DETAIL_MARKERS = (
    "这篇论文", "该论文", "那篇论文", "论文详情", "具体做了什么", "讲了什么",
    "paper details", "what does this paper",
)

_SEARCH_MARKERS = (
    "有哪些", "哪些论文", "相关文献", "相关论文", "检索", "找一下", "找找",
    "论文", "文献", "方法", "最新", "近年的", "关于", "search", "papers on",
    "literature", "paper about",
)

_CONCEPT_MARKERS = (
    "是什么", "什么是", "定义", "原理", "怎么工作", "如何工作", "如何实现",
    "概念", "解释一下", "what is", "definition", "how does", "how works",
)

_META_MARKERS = (
    "你是谁", "你是什么", "你能做什么", "能做什么", "还会什么", "除了科研",
    "能力边界", "局限", "怎么用", "如何使用", "谢谢", "再见",
    "who are you", "what can you", "thanks",
)

# Too short and/or tool-less to route — clarify instead of blind searching.
_VAGUE_PATTERNS = (
    re.compile(r"^[\s\W\d]*$"),            # punctuation/whitespace only
    re.compile(r"^(帮我|请|请问|看看|看一下|你好|hi|hello)[\s\W]*$", re.I),
    re.compile(r"^.{1,6}$"),               # very short with no clear subject
)


def _match_any(question: str, markers: tuple[str, ...]) -> str | None:
    lower = question.lower()
    for marker in markers:
        if marker in lower:
            return marker
    return None


def _skill_intent(question: str) -> IntentName | None:
    for name, marker in _SKILL_MARKERS:
        if marker in question:
            return name
    return None


def classify_intent(question: str) -> Intent:
    """Classify one user question into an :class:`Intent`.

    Priority: explicit skill prompt > claim check > review > trend > compare >
    graph > recommend > detail > search > concept > meta > vague > unknown.
    Deterministic: no LLM, no network, no randomness.
    """
    question = (question or "").strip()
    raw = question
    if not question:
        return _intent("unknown", "空问题")

    skill = _skill_intent(question)
    if skill:
        return _intent(skill, "命中 SciScope 技能标记")

    for name, markers, clue in (
        ("claim_verification", _CLAIM_MARKERS, "含论断核查类词"),
        ("field_review", _REVIEW_MARKERS, "含领域综述类词"),
        ("trend_analysis", _TREND_MARKERS, "含趋势分析类词"),
        ("paper_compare", _COMPARE_MARKERS, "含论文对比类词"),
        ("graph_query", _GRAPH_MARKERS, "含图谱查询类词"),
        ("paper_recommend", _RECOMMEND_MARKERS, "含推荐类词"),
        ("paper_detail", _DETAIL_MARKERS, "含论文详情类词"),
        # Meta/capability phrasing ("除了科研文献,你还会什么") must beat the
        # broad "文献/论文" search markers below, so it is checked first.
        ("meta_query", _META_MARKERS, "含能力说明类词"),
        ("literature_search", _SEARCH_MARKERS, "含文献检索类词"),
        ("concept_explanation", _CONCEPT_MARKERS, "含概念解释类词"),
    ):
        hit = _match_any(raw, markers)
        if hit:
            return _intent(name, f"命中关键词「{hit}」")

    # Meta/capability phrasing ("除了科研文献,你还会什么") is long but still a
    # capability question; the broad "文献" marker would otherwise misroute it.
    for marker in _META_MARKERS:
        if marker in raw.lower():
            return _intent("meta_query", f"命中关键词「{marker}」")

    stripped = re.sub(r"[\s\W]+", "", question)
    if not stripped or any(p.search(question) for p in _VAGUE_PATTERNS):
        return _intent("vague_query", "问题过短或缺少可检索主题")

    return _intent("unknown", "未命中已知意图模式")


def _intent(name: IntentName, reason: str) -> Intent:
    return Intent(
        name=name,
        label=INTENT_LABELS[name],
        primary_tool=INTENT_PRIMARY_TOOL[name],
        reason=reason,
    )


# --- Guidance injected into the model-visible messages ------------------------
# The model sees this steering text (it decides final tool calls); the SSE
# ``intent`` event only carries the label + reason above, never this block.

def _guidance(intent: Intent) -> str:
    tool = intent.primary_tool
    if tool is None:
        return ""
    if intent.name in {"claim_verification", "skill_claim_check"}:
        return (
            "这是论断核查类问题。第一动作必须调用 verify_claim 核查论断的文献证据,"
            "拿到其支持等级与证据立场后再回答;不要把论断核查偷换成普通文献检索,"
            "也不要未核查就直接下结论。"
        )
    return f"这是{intent.label}类问题,请优先调用 {tool} 获取证据后再回答。"


# Vague/unknown questions must not trigger blind searching. The exact phrasing
# stays in the model's hands; this only constrains behavior.
def clarification_guidance(intent: Intent) -> str:
    if intent.name == "vague_query":
        return "问题过于模糊、无法确定检索目标。请不要调用任何工具,先用一句话反问澄清用户想查什么。"
    if intent.name == "unknown":
        return (
            "未能识别问题意图。请不要盲目标发起检索;若无法确定用户想查什么,"
            "先用一句话反问澄清;若问题属于概念/常识类,直接回答即可。"
        )
    return ""


def routing_guidance(intent: Intent) -> str:
    """Full model-visible steering block for an intent ("" when no guidance)."""
    parts = [clarification_guidance(intent)]
    if intent.name not in {"vague_query", "unknown", "meta_query", "concept_explanation"}:
        parts.append(_guidance(intent))
    return "\n".join(p for p in parts if p)
