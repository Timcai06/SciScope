"""G02 图谱查询解释合同 —— 服务层（kg_asset_service）测试。

覆盖每类查询的成功 / 空结果 / 依赖缺失三态：
- 资产不存在（文件缺失）→ 结构化 unavailable + 固定 reason；
- schema_version 不匹配 → 结构化 unavailable + reason；
- 资产可用时 paper / source / topic / year 查询 → ok / empty；
- 成功响应带 asset schema_version、input_fingerprint、关系类型、
  来源 paper_id/source_id/hash 状态与诚实边界 note；
- 未知 kind / 空 value → 结构化响应，不抛异常。
"""

import json

import pytest

from backend.app.services import kg_asset_service
from src.infra.knowledge_graph_asset import build_knowledge_graph_asset

EXPECTED_SCHEMA_VERSION = "knowledge-graph-asset/v1"


@pytest.fixture
def asset_records():
    return [
        {"paper_id": "P1", "source": "arxiv", "source_id": "A1", "title": "Alpha",
         "year": 2024, "field": "computer science", "keywords": ["graph", "llm"]},
        {"paper_id": "P2", "source": "pubmed", "source_id": "B2", "title": "Beta",
         "year": 2025, "field": "biomedicine", "keywords": ["graph"]},
    ]


@pytest.fixture
def asset_file(tmp_path, asset_records):
    asset = build_knowledge_graph_asset(asset_records)
    path = tmp_path / "graph_asset.json"
    path.write_text(json.dumps(asset, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _reset_asset_cache():
    kg_asset_service.reset_asset_cache()
    yield
    kg_asset_service.reset_asset_cache()


def _point_at(monkeypatch, path):
    monkeypatch.setenv("SCISCOPE_KG_ASSET_PATH", str(path))
    kg_asset_service.reset_asset_cache()


# --- 依赖缺失三态 ------------------------------------------------------------


def test_asset_file_missing_returns_structured_unavailable(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path / "missing.json")
    resp = kg_asset_service.query("paper", "P1")
    assert resp["status"] == "unavailable"
    assert resp["results"] == []
    assert resp["unavailable_reason"].startswith("kg_asset_file_missing:")
    assert resp["asset"] is None


def test_schema_version_mismatch_returns_structured_unavailable(monkeypatch, tmp_path):
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"schema_version": "knowledge-graph-asset/v9", "nodes": [], "edges": []}), encoding="utf-8")
    _point_at(monkeypatch, path)
    resp = kg_asset_service.query("paper", "P1")
    assert resp["status"] == "unavailable"
    assert resp["unavailable_reason"].startswith("schema_version_mismatch:got=knowledge-graph-asset/v9")
    assert resp["asset"] is None


def test_invalid_json_returns_structured_unavailable(monkeypatch, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    _point_at(monkeypatch, path)
    resp = kg_asset_service.query("paper", "P1")
    assert resp["status"] == "unavailable"
    assert resp["unavailable_reason"] == "kg_asset_invalid_json"


def test_unsupported_kind_returns_structured_unavailable(monkeypatch, asset_file):
    _point_at(monkeypatch, asset_file)
    resp = kg_asset_service.query("community", "anything")
    assert resp["status"] == "unavailable"
    assert resp["unavailable_reason"].startswith("unsupported_kind:community")


def test_empty_value_returns_structured_empty(monkeypatch, asset_file):
    _point_at(monkeypatch, asset_file)
    resp = kg_asset_service.query("paper", "")
    assert resp["status"] == "empty"
    assert resp["results"] == []


# --- paper 查询 --------------------------------------------------------------


def test_paper_query_ok_carries_asset_meta_relations_and_provenance(monkeypatch, asset_file, asset_records):
    _point_at(monkeypatch, asset_file)
    resp = kg_asset_service.query("paper", "P1")

    assert resp["status"] == "ok"
    assert resp["data_source"] == "kg_asset_v1"
    # asset 元数据：schema_version + input_fingerprint。
    assert resp["asset"]["schema_version"] == EXPECTED_SCHEMA_VERSION
    assert resp["asset"]["input_fingerprint"]
    assert resp["asset"]["module_version"]

    results = resp["results"]
    assert results["paper"]["paper_id"] == "P1"
    assert results["paper"]["title"] == "Alpha"
    # 三类关系全部命中。
    relations = set(results["relations"])
    assert relations == {"published_in", "about", "published_in_year"}
    # 邻居边带 provenance：paper_id / source_id / hash 状态。
    for neighbour in results["neighbours"]:
        prov = neighbour["provenance"]
        assert prov["paper_id"] == "P1"
        assert prov["source_id"]
        assert prov["record_sha256"] is None  # corpus 无 D01 哈希
        assert prov["record_sha256_status"] == "d01_unavailable"
    assert "不构成因果" in resp["note"]


def test_paper_query_by_uid_also_matches(monkeypatch, asset_file):
    from src.infra.chunks import paper_uid

    _point_at(monkeypatch, asset_file)
    rec = {"paper_id": "P1", "source": "arxiv", "source_id": "A1", "title": "Alpha",
           "year": 2024, "field": "computer science", "keywords": ["graph", "llm"]}
    resp = kg_asset_service.query("paper", paper_uid(rec))
    assert resp["status"] == "ok"
    assert resp["results"]["paper"]["paper_id"] == "P1"


def test_paper_query_empty_for_unknown_paper(monkeypatch, asset_file):
    _point_at(monkeypatch, asset_file)
    resp = kg_asset_service.query("paper", "NOPE")
    assert resp["status"] == "empty"
    assert resp["results"] == []
    assert resp["asset"]["schema_version"] == EXPECTED_SCHEMA_VERSION


# --- source / topic / year 查询 -----------------------------------------------


def test_topic_query_ok_lists_papers(monkeypatch, asset_file):
    _point_at(monkeypatch, asset_file)
    resp = kg_asset_service.query("topic", "graph")
    assert resp["status"] == "ok"
    assert resp["results"]["entity"]["label"] == "graph"
    assert resp["results"]["paper_count"] == 2  # P1 与 P2 都有 graph
    assert set(resp["results"]["papers"]) == {"P1", "P2"}
    assert resp["results"]["provenance_sample"]["record_sha256_status"] == "d01_unavailable"


def test_source_query_ok_lists_papers(monkeypatch, asset_file):
    _point_at(monkeypatch, asset_file)
    resp = kg_asset_service.query("source", "arxiv")
    assert resp["status"] == "ok"
    assert resp["results"]["paper_count"] == 1
    assert resp["results"]["papers"] == ["P1"]


def test_year_query_ok_lists_papers(monkeypatch, asset_file):
    _point_at(monkeypatch, asset_file)
    resp = kg_asset_service.query("year", "2024")
    assert resp["status"] == "ok"
    assert resp["results"]["paper_count"] == 1
    assert resp["results"]["papers"] == ["P1"]


def test_entity_query_empty_for_unknown(monkeypatch, asset_file):
    _point_at(monkeypatch, asset_file)
    for kind in ("source", "topic", "year"):
        resp = kg_asset_service.query(kind, "does-not-exist")
        assert resp["status"] == "empty"
        assert resp["results"] == []
