"""G01 可追溯知识图谱资产构建器。

把**已有可验证字段**（``papers_corpus.json`` 形态：paper_id / title / source /
source_id / year / keywords / field）组织成可查询的最小知识图谱资产，为 G02
查询合同提供稳定输入。

本阶段诚实边界（对应 G01 计划）：
- 只做“可审计图谱资产”，不做大而全可视化，不重建 Web 图谱；
- 不接入 LLM、不做 embedding / full rebuild、不需要 2080 Ti；
- 不依赖 D03 未完成的关键信息抽取字段；接口为未来扩展预留，但不假装已有；
- 节点/边只表达**数据中已有可验证字段的关系**（来源、关键词、年份）；
  “共现关系”与“支持某科学结论”区分开——本资产不输出任何科学结论支持断言。

输出契约（供 G02 消费）：
- ``schema_version`` / ``module_version``：资产 schema 与构建器版本；
- ``build.input_fingerprint``：输入记录的规范化 sha256，用于审计输入版本；
- ``nodes``：Paper / Source / Topic / Year 四类节点；
- ``edges``：paper→source（published_in）、paper→topic（about）、
  paper→year（published_in_year）三类边；每条边携带 provenance
  （paper_id + source_id + record_sha256 + corpus_record_sha256 + record_sha256_status）；
- ``stats`` / ``warnings``：去重、空值、非法年份、未知来源的可查询处理记录。

哈希诚实语义（区分两个字段，不可混用）：
- ``record_sha256``：**真实 D01 合同哈希**，仅当输入记录自带该字段时保留；
  当前 ``papers_corpus.json`` 是处理后投影，不含 D01 的 license/usage_rights/
  原始文件哈希等合同字段，故此时为 ``null`` + ``record_sha256_status="d01_unavailable"``，
  不用于跨阶段回链；
- ``corpus_record_sha256``：对当前 processed corpus 投影现场计算的哈希
  （``compute_record_hash``，D01 哈希算法），仅供本资产内审计，不等于 D01 哈希。

可重复性：相同输入 → 字节级相同输出（不含时间戳），小样例可重复构建。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from src.data_contracts.admission import compute_record_hash
from src.infra.chunks import paper_uid

# 资产 schema 与构建器版本：任何不兼容的节点/边字段变更都必须升版本。
SCHEMA_VERSION = "knowledge-graph-asset/v1"
MODULE_VERSION = "1.0.0"

# 合法年份范围（仅整型且在范围内才建 Year 节点与 published_in_year 边）。
MIN_YEAR = 1000
MAX_YEAR = 2100

# 节点/边类型常量（schema 与输出共用，避免字符串漂移）。
NODE_PAPER = "paper"
NODE_SOURCE = "source"
NODE_TOPIC = "topic"
NODE_YEAR = "year"

EDGE_PAPER_SOURCE = "published_in"
EDGE_PAPER_TOPIC = "about"
EDGE_PAPER_YEAR = "published_in_year"

SCHEMA = {
    "schema_version": SCHEMA_VERSION,
    "node_types": {
        NODE_PAPER: {
            "id": "paper_uid（chunks.paper_uid(record)，复用现有链配方）",
            "properties": {
                "paper_id": "str，外部稳定论文标识",
                "source": "str，数据来源",
                "source_id": "str，来源内标识",
                "title": "str",
                "year": "int | None，原始值（非法年份不建 Year 节点）",
                "field": "str | None",
                "record_sha256": "str | None，真实 D01 合同哈希；corpus 无则 null（d01_unavailable）",
                "corpus_record_sha256": "str，processed corpus 投影的现场哈希（compute_record_hash）",
                "record_sha256_status": "d01_unavailable | verified | mismatch",
            },
        },
        NODE_SOURCE: {
            "id": "source:<source>",
            "properties": {"name": "str，来源名"},
        },
        NODE_TOPIC: {
            "id": "topic:<keyword>（原文去重，不做词形归一，避免丢失消歧括号）",
            "properties": {"keyword": "str，论文关键词原文"},
        },
        NODE_YEAR: {
            "id": "year:<yyyy>",
            "properties": {"year": "int，合法年份（MIN_YEAR..MAX_YEAR）"},
        },
    },
    "edge_types": {
        EDGE_PAPER_SOURCE: {"from": NODE_PAPER, "to": NODE_SOURCE, "meaning": "论文发布/收录于该来源"},
        EDGE_PAPER_TOPIC: {"from": NODE_PAPER, "to": NODE_TOPIC, "meaning": "论文标注了该关键词（数据已有字段，非抽取结论）"},
        EDGE_PAPER_YEAR: {"from": NODE_PAPER, "to": NODE_YEAR, "meaning": "论文发表于该年份（仅合法年份）"},
    },
    "edge_provenance": {
        "paper_id": "str，外部稳定论文标识",
        "source_id": "str，来源内标识",
        "record_sha256": "str | null，真实 D01 record_sha256（corpus 无 D01 合同字段时为 null）",
        "corpus_record_sha256": "str，processed corpus 投影的现场哈希（compute_record_hash）",
        "record_sha256_status": "d01_unavailable | verified | mismatch，D01 哈希可验证性",
    },
    "policy": {
        "duplicate_paper": "同一 paper_uid 只保留首条，后续记录跳过并记 warning",
        "missing_keywords": "keywords 为空/缺省 → 建 Paper 节点但不建 about 边，计入 stats.skipped",
        "invalid_year": "year 非 int 或越界 → 建 Paper 节点但不建 published_in_year 边，计入 stats.skipped",
        "unknown_source": "source 为空/缺省 → 不建 Source 节点与 published_in 边，计入 stats.skipped",
        "empty_keyword_item": "keywords 列表内空字符串项过滤，计入 stats.skipped",
        "record_sha256_semantics": "record_sha256 只表达真实 D01 合同哈希（corpus 无则 null/d01_unavailable）；corpus_record_sha256 是 processed corpus 投影的现场哈希，两者不可等同、不可用于跨阶段回链",
    },
}


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _is_valid_year(year: Any) -> bool:
    return isinstance(year, int) and MIN_YEAR <= year <= MAX_YEAR


def _record_hash_fields(record: dict[str, Any]) -> tuple[str | None, str, str]:
    """拆分 D01 合同哈希与 corpus 投影哈希，避免把现场哈希冒充 D01 record_sha256。

    返回 ``(record_sha256, corpus_record_sha256, status)``：
    - ``record_sha256``：输入记录里真实存在的 D01 合同哈希（corpus 无则 None）；
    - ``corpus_record_sha256``：对当前 processed corpus 投影现场计算（D01 语义）；
    - ``status``：d01_unavailable（输入无 D01 哈希）/ verified / mismatch。
    """
    corpus_record_sha256 = compute_record_hash(record)
    declared = _clean(record.get("record_sha256"))
    if not declared:
        return None, corpus_record_sha256, "d01_unavailable"
    if declared == corpus_record_sha256:
        return declared, corpus_record_sha256, "verified"
    return declared, corpus_record_sha256, "mismatch"


def _input_fingerprint(records: list[dict[str, Any]]) -> str:
    """输入记录的规范化 sha256（审计输入版本，不参与节点内容计算）。"""
    payload = json.dumps(records, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_knowledge_graph_asset(
    records: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """把论文记录构建为最小知识图谱资产。

    确定性：相同输入返回字节级相同结构（无时间戳、无随机量）。
    """
    record_list = [dict(r) for r in records]
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    stats: dict[str, Any] = {
        "input_records": len(record_list),
        "nodes": {NODE_PAPER: 0, NODE_SOURCE: 0, NODE_TOPIC: 0, NODE_YEAR: 0},
        "edges": {EDGE_PAPER_SOURCE: 0, EDGE_PAPER_TOPIC: 0, EDGE_PAPER_YEAR: 0},
        "skipped": {
            "duplicate_papers": 0,
            "source_edges": 0,
            "topic_edges": 0,
            "year_edges": 0,
            "empty_keyword_items": 0,
        },
    }
    warnings: list[dict[str, Any]] = []

    def _add_node(node: dict[str, Any]) -> None:
        ntype = node["type"]
        if node["id"] not in nodes:
            nodes[node["id"]] = node
            stats["nodes"][ntype] += 1

    def _add_edge(source: str, target: str, relation: str, provenance: dict[str, Any]) -> None:
        key = (source, target, relation)
        if key not in edges:
            edges[key] = {
                "source": source,
                "target": target,
                "relation": relation,
                "provenance": provenance,
            }
            stats["edges"][relation] += 1

    for record in record_list:
        paper_id = _clean(record.get("paper_id"))
        source = _clean(record.get("source"))
        source_id = _clean(record.get("source_id") or paper_id)
        record_sha256, corpus_record_sha256, record_sha256_status = _record_hash_fields(record)

        # paper 节点 id 直接复用 chunks.paper_uid（不复制近似配方）。
        paper_node_id = paper_uid(record)
        if paper_node_id in nodes:
            stats["skipped"]["duplicate_papers"] += 1
            warnings.append(
                {"type": "duplicate_paper", "paper_id": paper_id, "reason": "paper_uid 已存在，仅保留首条"}
            )
            continue

        year_value = record.get("year")
        provenance = {
            "paper_id": paper_id,
            "source_id": source_id,
            "record_sha256": record_sha256,
            "corpus_record_sha256": corpus_record_sha256,
            "record_sha256_status": record_sha256_status,
        }
        _add_node(
            {
                "id": paper_node_id,
                "type": NODE_PAPER,
                "label": _clean(record.get("title")) or paper_id,
                "properties": {
                    "paper_id": paper_id,
                    "source": source,
                    "source_id": source_id,
                    "title": _clean(record.get("title")),
                    "year": year_value if isinstance(year_value, int) else None,
                    "field": record.get("field"),
                    "record_sha256": record_sha256,
                    "corpus_record_sha256": corpus_record_sha256,
                    "record_sha256_status": record_sha256_status,
                },
            }
        )

        # Paper → Source（未知来源：不建边，只记可查询状态）。
        if source:
            source_id_node = f"source:{source}"
            _add_node({"id": source_id_node, "type": NODE_SOURCE, "label": source, "properties": {"name": source}})
            _add_edge(paper_node_id, source_id_node, EDGE_PAPER_SOURCE, provenance)
        else:
            stats["skipped"]["source_edges"] += 1
            warnings.append({"type": "unknown_source", "paper_id": paper_id, "reason": "source 为空，不建 published_in 边"})

        # Paper → Topic（缺关键词：建 Paper，不建 about 边）。
        keywords = record.get("keywords")
        if isinstance(keywords, list) and keywords:
            for keyword in keywords:
                kw = _clean(keyword)
                if not kw:
                    stats["skipped"]["empty_keyword_items"] += 1
                    warnings.append({"type": "empty_keyword_item", "paper_id": paper_id, "reason": "keywords 列表内含空项，已过滤"})
                    continue
                topic_node_id = f"topic:{kw}"
                _add_node({"id": topic_node_id, "type": NODE_TOPIC, "label": kw, "properties": {"keyword": kw}})
                _add_edge(paper_node_id, topic_node_id, EDGE_PAPER_TOPIC, provenance)
        else:
            stats["skipped"]["topic_edges"] += 1
            warnings.append({"type": "missing_keywords", "paper_id": paper_id, "reason": "keywords 为空/缺省，不建 about 边"})

        # Paper → Year（非法年份：建 Paper，不建 published_in_year 边）。
        if _is_valid_year(year_value):
            year_node_id = f"year:{int(year_value)}"
            _add_node({"id": year_node_id, "type": NODE_YEAR, "label": str(int(year_value)), "properties": {"year": int(year_value)}})
            _add_edge(paper_node_id, year_node_id, EDGE_PAPER_YEAR, provenance)
        else:
            stats["skipped"]["year_edges"] += 1
            warnings.append(
                {
                    "type": "invalid_year",
                    "paper_id": paper_id,
                    "reason": f"year={year_value!r} 非合法整型年份（{MIN_YEAR}..{MAX_YEAR}），不建 published_in_year 边",
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "build": {
            "input_records": len(record_list),
            "input_fingerprint": _input_fingerprint(record_list),
            "record_hash_scheme": "corpus_record_sha256=compute_record_hash（src.data_contracts.admission）；record_sha256 仅保留输入中真实 D01 合同哈希，corpus 无则 null/d01_unavailable",
            "node_id_scheme": "paper: chunks.paper_uid(record)；source/topic/year: 可读前缀 id",
        },
        "schema": SCHEMA,
        "nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
        "edges": [
            edges[k]
            for k in sorted(edges, key=lambda k: (k[0], k[2], k[1]))
        ],
        "stats": stats,
        "warnings": warnings,
    }


def write_knowledge_graph_asset(
    records: Iterable[dict[str, Any]],
    output_path: str | Path,
) -> dict[str, Any]:
    """构建并写入图谱资产 JSON；返回与 ``build_knowledge_graph_asset`` 相同的结构。

    输出字节级确定（相同输入 → 相同文件内容），小样例可重复构建。
    """
    asset = build_knowledge_graph_asset(records)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asset, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return asset
