"""G01 可追溯知识图谱资产测试。

覆盖验收：
- 固定小样例构建结果稳定、可重复（字节级确定性，写文件可重建）；
- 节点（Paper/Source/Topic/Year）、边（Paper→Source/Topic/Year）、
  provenance、版本、统计摘要均有测试；
- 去重/空值/非法年份/未知来源有明确策略与测试：
  重复论文、缺关键词、非法年份、未知来源、关键词列表内空项。
"""

import json

from src.data_contracts.admission import compute_record_hash
from src.infra.chunks import paper_uid
from src.infra.knowledge_graph_asset import (
    EDGE_PAPER_SOURCE,
    EDGE_PAPER_TOPIC,
    EDGE_PAPER_YEAR,
    NODE_PAPER,
    NODE_SOURCE,
    NODE_TOPIC,
    NODE_YEAR,
    SCHEMA,
    SCHEMA_VERSION,
    build_knowledge_graph_asset,
    write_knowledge_graph_asset,
)


def _sample_records():
    """最小固定样例：覆盖正常论文 + 去重/空值/非法/未知来源边界。"""
    return [
        {"paper_id": "P1", "source": "arxiv", "source_id": "A1", "title": "Alpha",
         "year": 2024, "field": "computer science", "keywords": ["graph", "llm"]},
        {"paper_id": "P2", "source": "pubmed", "source_id": "B2", "title": "Beta",
         "year": 2025, "field": "biomedicine", "keywords": ["graph"]},
        {"paper_id": "P1", "source": "arxiv", "source_id": "A1", "title": "Alpha dup",
         "year": 2024, "field": "computer science", "keywords": ["x"]},
        {"paper_id": "P3", "source": "", "source_id": "C3", "title": "Gamma",
         "year": "bad", "field": None, "keywords": []},
        {"paper_id": "P4", "source": "doaj", "source_id": "D4", "title": "Delta",
         "year": 9999, "field": None, "keywords": ["ok", ""]},
    ]


# --- 最小样例：节点与边类型 ------------------------------------------------


def test_minimal_sample_builds_all_node_and_edge_types():
    asset = build_knowledge_graph_asset(_sample_records())

    assert asset["schema_version"] == SCHEMA_VERSION
    assert asset["module_version"]
    assert asset["build"]["input_records"] == 5

    types = {n["type"] for n in asset["nodes"]}
    assert types == {NODE_PAPER, NODE_SOURCE, NODE_TOPIC, NODE_YEAR}
    assert asset["stats"]["nodes"][NODE_PAPER] == 4  # P1 重复被跳过，其余 3 + P1 首条 = 4

    relations = {e["relation"] for e in asset["edges"]}
    assert relations == {EDGE_PAPER_SOURCE, EDGE_PAPER_TOPIC, EDGE_PAPER_YEAR}


def test_paper_node_keeps_verifiable_fields():
    asset = build_knowledge_graph_asset([_sample_records()[0]])
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER)
    props = paper["properties"]
    assert props["paper_id"] == "P1"
    assert props["source"] == "arxiv"
    assert props["source_id"] == "A1"
    assert props["title"] == "Alpha"
    assert props["year"] == 2024
    assert props["field"] == "computer science"
    # corpus 无 D01 合同字段：record_sha256 必须为 null + d01_unavailable，
    # 只有 corpus_record_sha256 是现场投影哈希（诚实区分，不冒充 D01 哈希）。
    assert props["record_sha256"] is None
    assert props["record_sha256_status"] == "d01_unavailable"
    assert props["corpus_record_sha256"] == compute_record_hash(_sample_records()[0])


def test_paper_node_id_reuses_chunks_paper_uid():
    """直接复用 chunks.paper_uid(record)，不复制近似 ID 配方。"""
    record = _sample_records()[0]
    asset = build_knowledge_graph_asset([record])
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER)
    assert paper["id"] == paper_uid(record)


# --- provenance ------------------------------------------------------------


def test_every_edge_carries_provenance_with_corpus_sha256():
    asset = build_knowledge_graph_asset(_sample_records())
    # 样例含重复 P1：按 paper_id 取首条记录（与构建器“保留首条”策略一致）。
    records: dict[str, dict] = {}
    for r in _sample_records():
        records.setdefault(r["paper_id"], r)

    for edge in asset["edges"]:
        prov = edge["provenance"]
        assert prov["paper_id"]
        assert prov["source_id"]
        # corpus 输入无 D01 哈希：record_sha256 为 null，corpus_record_sha256 为现场哈希。
        assert prov["record_sha256"] is None
        assert prov["record_sha256_status"] == "d01_unavailable"
        assert prov["corpus_record_sha256"] == compute_record_hash(records[prov["paper_id"]])


def test_d01_record_sha256_preserved_when_present():
    """输入自带合法 D01 哈希时：保留 record_sha256 并标 verified，绝不覆盖。"""
    record = {"paper_id": "D1", "source": "iflytek", "source_id": "S1", "title": "D",
              "year": 2024, "field": None, "keywords": ["k"], "license": "cc0"}
    record["record_sha256"] = compute_record_hash(record)
    asset = build_knowledge_graph_asset([record])
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER)
    assert paper["properties"]["record_sha256"] == record["record_sha256"]
    assert paper["properties"]["record_sha256_status"] == "verified"
    for edge in asset["edges"]:
        assert edge["provenance"]["record_sha256"] == record["record_sha256"]
        assert edge["provenance"]["record_sha256_status"] == "verified"


def test_d01_record_sha256_mismatch_is_reported():
    record = {"paper_id": "M1", "source": "iflytek", "source_id": "S2", "title": "M",
              "year": 2024, "field": None, "keywords": [], "record_sha256": "0" * 64}
    asset = build_knowledge_graph_asset([record])
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER)
    assert paper["properties"]["record_sha256"] == "0" * 64
    assert paper["properties"]["record_sha256_status"] == "mismatch"


def test_provenance_points_to_the_emitting_paper():
    asset = build_knowledge_graph_asset(_sample_records()[0:1])
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER)

    for edge in asset["edges"]:
        assert edge["source"] == paper["id"]
        assert edge["provenance"]["paper_id"] == "P1"


# --- 版本与统计摘要 ----------------------------------------------------------


def test_output_carries_schema_version_build_and_stats():
    asset = build_knowledge_graph_asset(_sample_records())

    assert asset["schema"] == SCHEMA
    assert asset["schema"]["schema_version"] == SCHEMA_VERSION
    assert asset["build"]["input_fingerprint"]
    assert asset["build"]["record_hash_scheme"]
    assert set(asset["stats"]) == {"input_records", "nodes", "edges", "skipped"}
    assert isinstance(asset["warnings"], list)


def test_input_fingerprint_changes_with_input():
    a1 = build_knowledge_graph_asset(_sample_records()[0:1])
    a2 = build_knowledge_graph_asset(_sample_records()[0:2])
    assert a1["build"]["input_fingerprint"] != a2["build"]["input_fingerprint"]


# --- 可重复性 ---------------------------------------------------------------


def test_repeat_build_is_byte_deterministic():
    records = _sample_records()
    first = build_knowledge_graph_asset(records)
    second = build_knowledge_graph_asset(records)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_write_is_deterministic_and_reloadable(tmp_path):
    records = _sample_records()
    out = tmp_path / "graph_asset.json"
    write_knowledge_graph_asset(records, out)
    bytes_first = out.read_bytes()
    write_knowledge_graph_asset(records, out)
    assert out.read_bytes() == bytes_first  # 相同输入 → 字节级相同文件

    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["schema_version"] == SCHEMA_VERSION
    assert len(reloaded["nodes"]) == len(build_knowledge_graph_asset(records)["nodes"])


# --- 去重 / 空值 / 非法年份 / 未知来源策略 --------------------------------------


def test_duplicate_paper_keeps_first_and_skips_rest():
    asset = build_knowledge_graph_asset(_sample_records())

    assert asset["stats"]["skipped"]["duplicate_papers"] == 1
    assert any(w["type"] == "duplicate_paper" and w["paper_id"] == "P1" for w in asset["warnings"])
    # 只有一条 P1 的 paper 节点（首条），第二条被跳过。
    p1_nodes = [n for n in asset["nodes"] if n["type"] == NODE_PAPER and n["properties"]["paper_id"] == "P1"]
    assert len(p1_nodes) == 1
    assert p1_nodes[0]["properties"]["title"] == "Alpha"  # 保留首条


def test_missing_keywords_builds_paper_without_topic_edge():
    asset = build_knowledge_graph_asset(
        [{"paper_id": "P3", "source": "doaj", "source_id": "D3", "title": "Gamma",
          "year": 2023, "field": None, "keywords": []}]
    )
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER)
    assert paper["properties"]["paper_id"] == "P3"
    assert not [e for e in asset["edges"] if e["relation"] == EDGE_PAPER_TOPIC and e["source"] == paper["id"]]
    assert asset["stats"]["skipped"]["topic_edges"] == 1
    assert any(w["type"] == "missing_keywords" for w in asset["warnings"])


def test_invalid_years_skip_year_edge_but_keep_paper():
    cases = [None, "", "bad", 9999, 999.5]
    records = [
        {"paper_id": f"Y{i}", "source": "arxiv", "source_id": f"Y{i}", "title": f"Y{i}",
         "year": y, "field": None, "keywords": ["k"]}
        for i, y in enumerate(cases)
    ]
    records.append({"paper_id": "YOK", "source": "arxiv", "source_id": "YOK", "title": "YOK",
                    "year": 2024, "field": None, "keywords": ["k"]})
    asset = build_knowledge_graph_asset(records)

    year_edges = [e for e in asset["edges"] if e["relation"] == EDGE_PAPER_YEAR]
    assert len(year_edges) == 1  # 只有 YOK 的合法 2024
    assert year_edges[0]["target"] == "year:2024"
    assert asset["stats"]["skipped"]["year_edges"] == len(cases)
    assert sum(1 for w in asset["warnings"] if w["type"] == "invalid_year") == len(cases)


def test_unknown_source_skips_source_edge_but_keeps_paper():
    asset = build_knowledge_graph_asset(
        [{"paper_id": "PX", "source": "", "source_id": "SX", "title": "X",
          "year": 2020, "field": None, "keywords": ["k"]}]
    )
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER)
    assert not [e for e in asset["edges"] if e["relation"] == EDGE_PAPER_SOURCE and e["source"] == paper["id"]]
    assert not any(n["type"] == NODE_SOURCE for n in asset["nodes"])
    assert asset["stats"]["skipped"]["source_edges"] == 1
    assert any(w["type"] == "unknown_source" for w in asset["warnings"])


def test_empty_keyword_item_is_filtered_and_counted():
    asset = build_knowledge_graph_asset(
        [{"paper_id": "PK", "source": "doaj", "source_id": "SK", "title": "K",
          "year": 2022, "field": None, "keywords": ["ok", "", "  "]}]
    )
    topic_edges = [e for e in asset["edges"] if e["relation"] == EDGE_PAPER_TOPIC]
    assert len(topic_edges) == 1
    assert topic_edges[0]["target"] == "topic:ok"
    assert asset["stats"]["skipped"]["empty_keyword_items"] == 2
    assert sum(1 for w in asset["warnings"] if w["type"] == "empty_keyword_item") == 2


# --- 供 G02 的 schema 契约 ---------------------------------------------------


def test_schema_contract_is_consumable_by_g02():
    """G02 查询合同所需的稳定输入：schema 声明节点/边类型、provenance 与策略。"""
    assert set(SCHEMA["node_types"]) == {NODE_PAPER, NODE_SOURCE, NODE_TOPIC, NODE_YEAR}
    assert set(SCHEMA["edge_types"]) == {EDGE_PAPER_SOURCE, EDGE_PAPER_TOPIC, EDGE_PAPER_YEAR}
    assert set(SCHEMA["edge_provenance"]) == {
        "paper_id", "source_id", "record_sha256", "corpus_record_sha256", "record_sha256_status",
    }
    assert set(SCHEMA["policy"]) >= {
        "duplicate_paper", "missing_keywords", "invalid_year", "unknown_source", "empty_keyword_item",
        "record_sha256_semantics",
    }
    # 诚实边界：资产只表达数据中已有字段的关系，不输出科学结论支持断言。
    meanings = " ".join(v["meaning"] for v in SCHEMA["edge_types"].values())
    assert "共现" not in meanings or "非抽取结论" in meanings


def test_asset_supports_minimal_g02_query():
    """真正构建资产并执行一次最小查询（不是只检查 SCHEMA 常量）：
    给定 paper_id，返回其来源、主题、年份邻居与逐条 provenance。
    """
    asset = build_knowledge_graph_asset(_sample_records())
    paper = next(n for n in asset["nodes"] if n["type"] == NODE_PAPER and n["properties"]["paper_id"] == "P1")
    paper_id = paper["id"]

    # 最小查询：P1 的全部出边邻居（source/topic/year 三类）。
    neighbours = [
        {"target": e["target"], "relation": e["relation"], "provenance": e["provenance"]}
        for e in asset["edges"]
        if e["source"] == paper_id
    ]
    relations = {n["relation"] for n in neighbours}
    assert relations == {EDGE_PAPER_SOURCE, EDGE_PAPER_TOPIC, EDGE_PAPER_YEAR}
    targets = {n["target"] for n in neighbours}
    assert "source:arxiv" in targets
    assert {"topic:graph", "topic:llm"} <= targets
    assert "year:2024" in targets
    # 每条结果都带回链：provenance.paper_id 指向 P1。
    assert all(n["provenance"]["paper_id"] == "P1" for n in neighbours)
    # 邻居节点可在同一资产内解析（供 G02 实体解释）。
    node_ids = {n["id"] for n in asset["nodes"]}
    assert all(n["target"] in node_ids for n in neighbours)
