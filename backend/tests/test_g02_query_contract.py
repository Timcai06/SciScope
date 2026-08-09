"""G02 查询解释合同 —— 工具层测试（query_knowledge_graph / recommend_papers / get_trends）。

每类查询至少覆盖：成功 / 空结果 / 依赖缺失 三种结构化响应，且：
- 图谱：资产可用 → kg_asset_v1 并带版本/指纹/关系/provenance；
  资产不可用 → 不静默换源（keyword/topic 显式降级旧路径并写明原因，
  paper/source/year 结构化 unavailable）；
- 推荐：paper_embeddings 缺失 → 固定 reason 的 unavailable，绝不伪造成功；
- 趋势：带数据版本/时间范围/预测“未经历史验证”标注；文件缺失 → unavailable。
"""

import json
from pathlib import Path

import pytest
from unittest import mock

from backend.app.agent.tools import get_trends, query_knowledge_graph, recommend_papers
from backend.app.agent.tools.recommend_papers import UNAVAILABLE_REASON
from src.infra.knowledge_graph_asset import build_knowledge_graph_asset


def _sample_asset() -> dict:
    return build_knowledge_graph_asset(
        [
            {"paper_id": "P1", "source": "arxiv", "source_id": "A1", "title": "Alpha",
             "year": 2024, "field": "computer science", "keywords": ["graph", "llm"]},
            {"paper_id": "P2", "source": "pubmed", "source_id": "B2", "title": "Beta",
             "year": 2025, "field": "biomedicine", "keywords": ["graph"]},
        ]
    )


@pytest.fixture
def asset_env(tmp_path, monkeypatch):
    from backend.app.services import kg_asset_service

    path = tmp_path / "graph_asset.json"
    path.write_text(json.dumps(_sample_asset(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("SCISCOPE_KG_ASSET_PATH", str(path))
    kg_asset_service.reset_asset_cache()
    yield
    kg_asset_service.reset_asset_cache()


@pytest.fixture
def no_asset_env(monkeypatch):
    from backend.app.services import kg_asset_service

    monkeypatch.setenv("SCISCOPE_KG_ASSET_PATH", str(Path("/nonexistent/graph_asset.json")))
    kg_asset_service.reset_asset_cache()
    yield
    kg_asset_service.reset_asset_cache()


# ===================== query_knowledge_graph =====================


def test_kg_query_paper_ok_from_asset(asset_env):
    out = json.loads(query_knowledge_graph.run({"type": "paper", "center": "P1"}))
    assert out["status"] == "ok"
    assert out["data_source"] == "kg_asset_v1"
    assert out["asset"]["schema_version"] == "knowledge-graph-asset/v1"
    assert out["asset"]["input_fingerprint"]
    assert set(out["results"]["relations"]) == {"published_in", "about", "published_in_year"}
    assert "不构成因果" in out["note"]


def test_kg_query_empty_result_is_structured(asset_env):
    out = json.loads(query_knowledge_graph.run({"type": "paper", "center": "NOPE"}))
    assert out["status"] == "empty"
    assert out["results"] == []


def test_kg_query_paper_unavailable_without_asset(no_asset_env):
    # 资产不可用且旧路径无等价查询 → 结构化 unavailable，不换源伪装。
    out = json.loads(query_knowledge_graph.run({"type": "paper", "center": "P1"}))
    assert out["status"] == "unavailable"
    assert out["unavailable_reason"].startswith("kg_asset_unavailable:kg_asset_file_missing:")


def test_kg_query_keyword_degrades_to_legacy_with_reason(no_asset_env):
    # keyword/topic：资产不可用时显式降级旧路径并写明原因（不静默）。
    out = json.loads(query_knowledge_graph.run({"type": "keyword", "center": "cancer"}))
    assert out["data_source"] == "legacy_graph_export"
    assert out["degraded_reason"].startswith("kg_asset_unavailable:")
    # 旧图谱存在且有结果 → ok（status 统一，不伪装）。
    assert out["status"] in ("ok", "empty")


def test_kg_query_legacy_unavailable_when_graph_also_missing(no_asset_env, monkeypatch):
    """资产与旧图谱都缺失时：明确 unavailable，不得伪装成可用（复核意见 2）。

    同时模拟 is_available=False 与 graph() 返回空图（真实缺失场景：导出文件不存在
    时 graph() 的 _load 也返回空图），断言三态一致。
    """
    monkeypatch.setattr(
        "backend.app.agent.tools.query_knowledge_graph.graph_service.is_available", lambda: False)
    monkeypatch.setattr(
        "backend.app.agent.tools.query_knowledge_graph.graph_service.graph",
        lambda *a, **k: {"type": "keyword", "nodes": [], "edges": []})
    out = json.loads(query_knowledge_graph.run({"type": "keyword", "center": "cancer"}))
    assert out["status"] == "unavailable"
    assert out["unavailable_reason"] == "legacy_graph_export_unavailable"
    assert out["node_count"] == 0
    assert out["edge_count"] == 0


def test_kg_query_legacy_empty_when_center_has_no_results(no_asset_env):
    """旧图谱存在但中心无结果 → empty（不是 unavailable，也不是 ok）。"""
    out = json.loads(query_knowledge_graph.run({"type": "keyword", "center": "zzzz-no-such-keyword-xyz"}))
    assert out["status"] == "empty"
    assert out["node_count"] == 0
    assert out["edge_count"] == 0


def test_kg_query_community_uses_legacy(no_asset_env):
    out = json.loads(query_knowledge_graph.run({"type": "community"}))
    assert out["data_source"] == "legacy_graph_export"
    assert "results" in out


def test_kg_query_unknown_type_structured(asset_env):
    out = json.loads(query_knowledge_graph.run({"type": "galaxy", "center": "x"}))
    assert out["status"] == "unavailable"
    assert out["unavailable_reason"].startswith("unsupported_kind:")


# ===================== recommend_papers =====================


def test_recommend_unavailable_when_embeddings_missing():
    with mock.patch("backend.app.services.recommend_service.is_available", return_value=False):
        out = json.loads(recommend_papers.run({"paper_id": "W123"}))
    assert out["status"] == "unavailable"
    assert out["unavailable_reason"] == UNAVAILABLE_REASON == "paper_embeddings_unavailable"
    assert out["results"] == []


def test_recommend_empty_when_no_candidates():
    with mock.patch("backend.app.services.recommend_service.is_available", return_value=True), \
         mock.patch("backend.app.services.recommend_service.recommend", return_value=[]):
        out = json.loads(recommend_papers.run({"paper_id": "W123"}))
    assert out["status"] == "empty"
    assert out["results"] == []


def test_recommend_ok_with_real_service_shaped_results():
    rec = mock.Mock()
    rec.paper_id = "W456"
    rec.title = "A paper"
    rec.year = 2024
    rec.field = "computer science"
    rec.semantic_similarity = 0.81
    rec.shared_keywords = ["graph"]
    rec.factors = {"semantic": 0.48}
    with mock.patch("backend.app.services.recommend_service.is_available", return_value=True), \
         mock.patch("backend.app.services.recommend_service.recommend", return_value=[rec]):
        out = json.loads(recommend_papers.run({"paper_id": "W123"}))
    assert out["status"] == "ok"
    assert out["data_source"] == "recommend_service"
    assert out["results"][0]["paper_id"] == "W456"
    assert out["results"][0]["factors"]["semantic"] == 0.48


def test_recommend_empty_without_paper_id():
    out = json.loads(recommend_papers.run({"paper_id": ""}))
    assert out["status"] == "empty"


# ===================== get_trends =====================


def test_get_trends_ok_carries_time_range_and_data_version():
    out = json.loads(get_trends.run({"keyword": "retrieval augmented generation"}))
    assert out["status"] == "ok"
    assert out["data_source"] == "trend_assets"
    # 版本 provenance 不混源：data_versions 记录全部输入文件；time_range 标注来源。
    assert len(out["asset"]["data_versions"]) >= 1
    assert out["asset"]["data_versions"][0]["present"] is True
    assert out["asset"]["time_range"]["range"] == "2022-2026"
    assert out["asset"]["time_range"]["ytd"] is True
    assert out["asset"]["time_range"]["source"]  # 明确时间范围来自哪个文件
    assert out["results"] and out["results"][0]["关键词"]
    # G04a 回测未通过时，出口必须明确降级为描述性趋势，不输出未来预测数值。
    assert out["trend_policy"]["descriptive_only"] is True
    assert "仅提供历史统计描述" in out["note"]
    assert all("预测" not in key and "forecast" not in key.lower() for key in out["results"][0])
    assert "不提供未来数值预测" in out["note"]


def test_get_trends_hot_result_records_both_input_versions(tmp_path, monkeypatch):
    """热点结果内容来自 hot_keywords.csv，但时间范围来自 keyword_trends.csv：
    两个输入文件的版本都必须记录，且 time_range.source 必须指向推导来源。
    """
    # 真实数据：hot 命中（retrieval augmented generation 是 hot_keywords.csv 首行）。
    out = json.loads(get_trends.run({"keyword": "retrieval augmented generation"}))
    versions = out["asset"]["data_versions"]
    paths = {v["path"] for v in versions}
    assert any("hot_keywords.csv" in p for p in paths)
    assert any("keyword_trends.csv" in p for p in paths)
    # 时间范围来自 keyword_trends.csv（hot 表头无年份列），必须显式标注来源。
    assert "keyword_trends.csv" in out["asset"]["time_range"]["source"]


def test_get_trends_empty_for_unknown_keyword():
    out = json.loads(get_trends.run({"keyword": "zzzz definitely not a keyword"}))
    assert out["status"] == "empty"
    assert out["results"] == []


def test_get_trends_unavailable_when_data_missing(tmp_path, monkeypatch):
    # 指向不存在的趋势数据目录：结构化 unavailable，reason 固定。
    monkeypatch.chdir(tmp_path)
    out = json.loads(get_trends.run({"keyword": "anything"}))
    assert out["status"] == "unavailable"
    assert out["unavailable_reason"] == "trend_data_unavailable"


def test_get_trends_empty_without_keyword():
    out = json.loads(get_trends.run({"keyword": ""}))
    assert out["status"] == "empty"
