"""get_trends matching, direction labeling, and miss suggestions.

The experience run (2026-07) surfaced three failure modes this file pins:
a hyphenated query missing its indexed keyword, a compound query missing with
no way to recover, and the English direction value being misread as growth.
"""

from __future__ import annotations

import json

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


def test_variant_key_folds_singular_plural():
    assert T._variant_key("graph neural networks gnn") == T._variant_key("graph neural network gnn")
    assert T._variant_key("federated learning") != T._variant_key("transfer learning")


def test_fold_variants_groups_conflicting_directions():
    # The real GNN case: two spellings, independently computed, opposite trends.
    matches = [
        {"keyword": "graph neural networks gnn", "doc_count": "50", "mk_trend": "falling"},
        {"keyword": "graph neural network gnn", "doc_count": "39", "mk_trend": "rising"},
    ]
    folded = T._fold_variants(matches)
    assert len(folded) == 1
    rep, variants, conflicting = folded[0]
    assert rep["keyword"] == "graph neural networks gnn"  # best-ranked kept
    assert variants == ["graph neural network gnn"]
    assert conflicting is True


def test_fold_variants_keeps_distinct_keywords_separate():
    matches = [
        {"keyword": "federated learning", "doc_count": "300", "mk_trend": "rising"},
        {"keyword": "split federated learning", "doc_count": "20", "mk_trend": "rising"},
    ]
    folded = T._fold_variants(matches)
    assert len(folded) == 2
    assert all(not conflicting for _, _, conflicting in folded)


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


def _write_hot_trend_fixture(tmp_path, monkeypatch, backtest_payload=None):
    hot = tmp_path / "models" / "trends"
    hot.mkdir(parents=True)
    (hot / "hot_keywords.csv").write_text(
        "keyword,doc_count,mk_trend,mk_p,sen_slope,momentum_score,burst_score,"
        "forecast_next_year,forecast_normalized_df,lifecycle_stage\n"
        "cancer,100,rising,0.01,0.1,0.2,0.3,2026,0.42,growing\n",
        encoding="utf-8",
    )
    if backtest_payload is not None:
        path = tmp_path / "backtest.json"
        path.write_text(json.dumps(backtest_payload), encoding="utf-8")
        monkeypatch.setenv("SCISCOPE_TRENDS_BACKTEST_PATH", str(path))
    else:
        monkeypatch.setenv("SCISCOPE_TRENDS_BACKTEST_PATH", str(tmp_path / "missing-backtest.json"))
    monkeypatch.chdir(tmp_path)


def test_get_trends_hides_forecasts_when_backtest_is_descriptive(tmp_path, monkeypatch):
    _write_hot_trend_fixture(
        tmp_path,
        monkeypatch,
        {"schema_version": "trends-backtest/v1", "decision": {"descriptive_only": True, "reason": "mae_wins=0/2"}},
    )
    payload = json.loads(T.run({"keyword": "cancer"}))
    item = payload["results"][0]

    assert payload["trend_policy"]["descriptive_only"] is True
    assert "预测目标年份(未验证外推)" not in item
    assert "预测目标年份(受约束外推)" not in item
    assert "forecast_next_year" not in json.dumps(item, ensure_ascii=False)
    assert "forecast_normalized_df" not in json.dumps(item, ensure_ascii=False)


def test_get_trends_fails_closed_when_backtest_missing(tmp_path, monkeypatch):
    _write_hot_trend_fixture(tmp_path, monkeypatch)
    payload = json.loads(T.run({"keyword": "cancer"}))

    assert payload["trend_policy"]["descriptive_only"] is True
    assert payload["trend_policy"]["reason"] == "trend_backtest_unavailable_fail_closed"
    assert "预测目标年份(未验证外推)" not in json.dumps(payload, ensure_ascii=False)


def test_get_trends_exposes_constrained_forecast_only_after_passing_backtest(tmp_path, monkeypatch):
    _write_hot_trend_fixture(
        tmp_path,
        monkeypatch,
        {"schema_version": "trends-backtest/v1", "decision": {"descriptive_only": False, "reason": "all_passed"}},
    )
    payload = json.loads(T.run({"keyword": "cancer"}))
    item = payload["results"][0]

    assert payload["trend_policy"]["descriptive_only"] is False
    assert item["预测目标年份(受约束外推)"] == "2026"
    assert item["该年外推归一化词频"] == "0.42"
