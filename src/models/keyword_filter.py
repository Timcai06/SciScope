"""Keyword noise filter for trend and graph models.

The raw keyword pool is polluted by two kinds of non-keywords that dominate the
high-frequency tail and distort trends / keyword graphs:

1. arXiv / classification category codes — e.g. ``cs.lg``, ``cs.ai``,
   ``stat.ml``, ``eess.iv``, ``cond-mat.mtrl-sci``, ``q-bio.ot``.
2. Overly generic discipline labels (top-level OpenAlex concepts) — e.g.
   ``computer science``, ``chemistry``, ``biology``, ``engineering`` — too broad
   to be a research hotspot.

Specific research terms (``machine learning``, ``knowledge graph``,
``drug discovery``, ``catalysis`` ...) are intentionally kept.

维护级口径（不可变）：
* “噪词”是跨图谱/趋势流水线共享的统一口径：分类代码、过宽泛学科名、
  场景化期刊片段，三类都不应进入热点和图谱的可检索口径。
* 过滤目标为字符串级别布尔判定，返回 True 即整体剔除，不保留降权策略。
* 同义/拼接式泄漏（如 `". "` 拼接词）按一票否决处理，避免把大量元数据术语误判为关键词。
"""

from __future__ import annotations

import re

# Lowercase dot-separated classification codes: cs.lg, stat.ml, eess.iv,
# cond-mat.mtrl-sci, q-bio.ot, math.oc ...
_CATEGORY_CODE_RE = re.compile(r"^[a-z]{1,8}(?:-[a-z]{2,})?\.[a-z.-]{1,12}$")

# Space-mangled arXiv codes (dots/hyphens stripped during tokenization):
# "cs lg", "q bio ot", "cond mat", "eess iv", "astro ph", "hep ph" ...
_ARXIV_ARCHIVES = (
    "cs", "stat", "eess", "math", "physics", "q bio", "q fin", "cond mat",
    "astro ph", "hep ph", "hep th", "hep ex", "hep lat", "quant ph", "nlin",
    "gr qc", "math ph", "nucl th", "nucl ex",
)
_SPACE_CODE_RE = re.compile(
    r"^(?:" + "|".join(a.replace(" ", r"\s") for a in _ARXIV_ARCHIVES) + r")(?:\s[a-z]{1,3})?$"
)

# OpenAlex concept disambiguation suffix, e.g. "context (archaeology)".
_DISAMBIG_RE = re.compile(r"\([a-z][a-z \-/]{2,30}\)\s*$")

# Journal / venue name fragments — these leak from source "concept" fields.
_VENUE_SUBSTRINGS = (
    "journal of", "frontiers in", "international journal", "transactions on",
    "proceedings of", "annals of", "bulletin of", "lecture notes", "review of",
    "advances in", "ieee transactions", "acm transactions", " review)", "reviews of",
)
_VENUE_EXACT = {
    "plos one", "scientific report", "scientific reports", "nature", "science",
    "nature communications", "cureus", "elife", "peerj", "heliyon", "ieee access",
    "sensors", "molecules", "materials", "energies", "sustainability",
    "applied sciences", "omega", "eye london england", "scientific data",
    "communications biology", "communications physics", "npj", "iscience",
    "cureu", "cureus", "medical science educator", "medical research",
}

# Standalone journal-title fragments (titles without "journal of ..." markers).
_VENUE_SUBSTRINGS_EXTRA = (
    "and related research", "and emerging disease", "dordrecht netherland",
    "clinical orthopaedics", "cellular oncology",
)

# Top-level discipline labels that are too generic to be keywords.
_GENERIC_LABELS = {
    "computer science", "artificial intelligence", "machine learning",
    "chemistry", "biology", "physics", "medicine", "mathematics",
    "engineering", "materials science", "nanotechnology", "data science",
    "theoretical computer science", "computational biology", "biochemistry",
    "computational science", "computer engineering", "applied mathematics",
    "natural science", "science", "technology", "research", "analysis",
    "biomedical engineering", "molecular biology", "cell biology",
    "environmental science", "social science", "psychology", "economics",
    "political science", "geology", "geography", "philosophy", "history",
    "art", "business", "sociology", "law", "physical sciences",
    "life sciences", "health sciences", "social sciences", "graph",
    "algorithm", "data", "model", "method", "system", "network",
    "artificial neural network", "neural network",
}


def is_noise_keyword(keyword: str) -> bool:
    """True if the keyword is a category code or an overly generic label."""
    kw = (keyword or "").strip().lower()
    if not kw or len(kw) <= 1:
        return True
    # 第一层：分类代码（cs.lg / stat.ml / q-bio.ot / q bio ot ...）直接剔除；
    # 第二层：学科/期刊噪词（严格匹配 + 子串匹配）直接剔除；
    # 第三层：OpenAlex 概念消岐括号/“foo. bar”拼接也剔除，避免误入趋势。
    if _CATEGORY_CODE_RE.match(kw) or _SPACE_CODE_RE.match(kw):
        return True
    if kw in _GENERIC_LABELS or kw in _VENUE_EXACT:
        return True
    if any(frag in kw for frag in _VENUE_SUBSTRINGS):
        return True
    if any(frag in kw for frag in _VENUE_SUBSTRINGS_EXTRA):
        return True
    # OpenAlex concept disambiguation, e.g. "pattern recognition (psychology)",
    # "context (archaeology)" — drop the parenthetical-discipline form.
    if _DISAMBIG_RE.search(kw):
        return True
    # Library-of-Congress style concatenated category labels, e.g.
    # "electronic computers. computer science" — research keywords don't use ". ".
    if ". " in kw:
        return True
    return False
