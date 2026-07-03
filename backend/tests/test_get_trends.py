"""get_trends matching, direction labeling, and miss suggestions.

The experience run (2026-07) surfaced three failure modes this file pins:
a hyphenated query missing its indexed keyword, a compound query missing with
no way to recover, and the English direction value being misread as growth.
"""

from __future__ import annotations

from backend.app.agent.tools import get_trends as T


def _row(keyword: str, doc_count: int = 10) -> dict:
    return {"keyword": keyword, "doc_count": str(doc_count)}


def test_normalize_folds_case_and_punctuation():
    assert T._normalize("Retrieval-Augmented Generation") == "retrieval augmented generation"
    assert T._normalize("  graph   neural\tnetworks ") == "graph neural networks"


def test_kw_match_hits_through_hyphens():
    rows = [_row("retrieval augmented generation", 5588), _row("document retrieval", 100)]
    hits = T._kw_match(rows, "Retrieval-Augmented Generation")
    assert hits and hits[0]["keyword"] == "retrieval augmented generation"


def test_kw_match_prefers_exact_then_doc_count():
    rows = [
        _row("graph neural networks gnn", 50),
        _row("graph neural network", 5),
        _row("graph neural networks in biology", 500),
    ]
    hits = T._kw_match(rows, "graph neural network")
    assert hits[0]["keyword"] == "graph neural network"  # exact wins over doc_count


def test_suggest_ranks_token_overlap_over_popularity():
    rows = [
        _row("multimodal learning", 9999),
        _row("federated learning", 300),
        _row("privacy preserving machine learning", 200),
        _row("unrelated topic", 100),
    ]
    suggestions = T._suggest(rows, "federated learning privacy")
    # Two shared tokens beat one, regardless of doc_count; no unrelated entries.
    assert suggestions[0] == "federated learning"
    assert "unrelated topic" not in suggestions


def test_suggest_dedupes_rows_across_tables():
    rows = [_row("federated learning", 300), _row("federated learning", 300)]
    assert T._suggest(rows, "federated learning privacy") == ["federated learning"]


def test_significance_verbalizes_p_value():
    assert T._significance("0.001").startswith("显著")
    assert "不显著" in T._significance("0.31")
    assert "不要下强结论" in T._significance("1.0")
    assert T._significance("") == "未知"


def test_direction_is_spelled_out_in_chinese():
    assert T._direction_cn("falling") == "falling(下降)"
    assert T._direction_cn("increasing") == "increasing(上升)"
    assert T._direction_cn("no-trend") == "no-trend(无明显趋势)"
    assert T._direction_cn("unknown-value") == "unknown-value"  # pass through
