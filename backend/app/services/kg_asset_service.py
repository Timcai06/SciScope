"""G02 图谱查询解释合同适配层：把 G01 的 ``knowledge-graph-asset/v1`` 变成可查询资产。

服务层只做三件事：
1. 按 ``SCISCOPE_KG_ASSET_PATH``（默认 ``output/knowledge_graph/graph_asset.json``）
   加载 G01 资产，并校验 ``schema_version``；
2. 对 paper / source / topic / year 四类实体提供最小查询（邻居边 + provenance）；
3. 对“资产不存在 / 版本不匹配 / 无匹配”返回**结构化** ok/empty/unavailable 响应，
   绝不抛裸异常。

诚实边界（写入每个成功响应的 ``note``）：
资产中的关系只表达论文**已有字段**（来源/关键词/年份）的关系，不构成因果，
也不构成任何 stance 支持结论（后者只能由 E 线 L3 给出）。
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA_VERSION = "knowledge-graph-asset/v1"

# 读取路径可通过环境变量注入（G02 要求）；默认值与 G01 全量重建命令一致。
DEFAULT_ASSET_PATH = "output/knowledge_graph/graph_asset.json"

# 诚实边界说明，随每个成功/空响应返回。
HONESTY_NOTE = (
    "本图谱关系仅表达论文已有字段（来源/关键词/年份）的关系，不构成因果，"
    "也不构成对任何科学结论或 stance 的支持。"
)

# 资产支持的查询 kind（community 等概览能力仍走旧 graph_service 路径）。
SUPPORTED_KINDS = ("paper", "source", "topic", "year")


def asset_path() -> str:
    """返回注入的资产路径（环境变量优先，否则默认路径）。"""
    return os.getenv("SCISCOPE_KG_ASSET_PATH", DEFAULT_ASSET_PATH)


@lru_cache(maxsize=1)
def _load_asset_cached() -> dict[str, Any] | None:
    """加载并校验资产；失败返回 None（原因经 ``_load_asset`` 记录）。"""
    return _load_asset()


def _load_asset() -> dict[str, Any] | None:
    """加载资产（无缓存）。文件缺失 / 版本不匹配 / JSON 损坏 → None。"""
    path = Path(asset_path())
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if raw.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        return None
    return raw


def load_asset() -> dict[str, Any] | None:
    """对外加载入口（带缓存）。"""
    return _load_asset_cached()


def reset_asset_cache() -> None:
    """测试用：清除资产缓存，便于注入不同路径/内容。"""
    _load_asset_cached.cache_clear()


def asset_unavailable_reason() -> str | None:
    """返回资产不可用的固定原因；资产可用返回 None。

    供工具层区分「资产不存在 / 版本不匹配 / 损坏」，reason 可测试。
    """
    path = Path(asset_path())
    if not path.is_file():
        return f"kg_asset_file_missing:{path}"
    raw = None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "kg_asset_invalid_json"
    if raw.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        return f"schema_version_mismatch:got={raw.get('schema_version')},expected={EXPECTED_SCHEMA_VERSION}"
    return None


def _asset_meta(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": asset.get("schema_version"),
        "module_version": asset.get("module_version"),
        "input_fingerprint": asset.get("build", {}).get("input_fingerprint"),
    }


def _paper_matches(node: dict[str, Any], value: str) -> bool:
    if node.get("type") != "paper":
        return False
    props = node.get("properties", {})
    return str(props.get("paper_id")) == value or node.get("id") == value


def _entity_matches(node: dict[str, Any], kind: str, value: str) -> bool:
    if node.get("type") != kind:
        return False
    return node.get("id") == value or node.get("label") == value


def _neighbour_summary(asset: dict[str, Any], paper_id: str, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按边整理邻居：目标节点 + 关系类型 + 来源 paper_id/source_id/hash 状态。"""
    node_by_id = {n["id"]: n for n in asset.get("nodes", [])}
    out: list[dict[str, Any]] = []
    for edge in edges:
        target = node_by_id.get(edge.get("target"))
        prov = edge.get("provenance", {})
        out.append(
            {
                "relation": edge.get("relation"),
                "target_id": edge.get("target"),
                "target_type": (target or {}).get("type"),
                "target_label": (target or {}).get("label"),
                "provenance": {
                    "paper_id": prov.get("paper_id"),
                    "source_id": prov.get("source_id"),
                    "record_sha256": prov.get("record_sha256"),
                    "corpus_record_sha256": prov.get("corpus_record_sha256"),
                    "record_sha256_status": prov.get("record_sha256_status"),
                },
            }
        )
    return out


def query(kind: str, value: str, asset: dict[str, Any] | None = None) -> dict[str, Any]:
    """统一查询入口，返回结构化三态响应（ok / empty / unavailable）。

    - kind：paper | source | topic | year
    - value：实体 id（paper_uid / source:xx / topic:xx / year:xxxx）或可读 label
    """
    value = str(value or "").strip()
    if kind not in SUPPORTED_KINDS:
        return {
            "status": "unavailable",
            "query": {"kind": kind, "value": value},
            "data_source": None,
            "asset": None,
            "results": [],
            "unavailable_reason": f"unsupported_kind:{kind}",
            "note": HONESTY_NOTE,
        }
    if not value:
        return {
            "status": "empty",
            "query": {"kind": kind, "value": value},
            "data_source": "kg_asset_v1" if asset is not None else None,
            "asset": _asset_meta(asset) if asset else None,
            "results": [],
            "unavailable_reason": None,
            "note": HONESTY_NOTE,
        }

    if asset is None:
        asset = load_asset()
    if asset is None:
        return {
            "status": "unavailable",
            "query": {"kind": kind, "value": value},
            "data_source": None,
            "asset": None,
            "results": [],
            "unavailable_reason": asset_unavailable_reason(),
            "note": HONESTY_NOTE,
        }

    meta = _asset_meta(asset)
    nodes = asset.get("nodes", [])
    edges = asset.get("edges", [])

    if kind == "paper":
        paper = next((n for n in nodes if _paper_matches(n, value)), None)
        if paper is None:
            return {
                "status": "empty",
                "query": {"kind": kind, "value": value},
                "data_source": "kg_asset_v1",
                "asset": meta,
                "results": [],
                "unavailable_reason": None,
                "note": HONESTY_NOTE,
            }
        paper_edges = [e for e in edges if e.get("source") == paper["id"]]
        return {
            "status": "ok",
            "query": {"kind": kind, "value": value},
            "data_source": "kg_asset_v1",
            "asset": meta,
            "results": {
                "paper": {
                    "id": paper["id"],
                    "paper_id": paper.get("properties", {}).get("paper_id"),
                    "title": paper.get("properties", {}).get("title"),
                    "year": paper.get("properties", {}).get("year"),
                    "record_sha256_status": paper.get("properties", {}).get("record_sha256_status"),
                },
                "relations": {
                    e.get("relation"): _neighbour_summary(asset, paper["id"], [e])[0]
                    for e in paper_edges
                },
                "neighbours": _neighbour_summary(asset, paper["id"], paper_edges),
            },
            "unavailable_reason": None,
            "note": HONESTY_NOTE,
        }

    # source / topic / year：返回关联论文列表。
    entity = next((n for n in nodes if _entity_matches(n, kind, value)), None)
    if entity is None:
        return {
            "status": "empty",
            "query": {"kind": kind, "value": value},
            "data_source": "kg_asset_v1",
            "asset": meta,
            "results": [],
            "unavailable_reason": None,
            "note": HONESTY_NOTE,
        }
    inbound = [e for e in edges if e.get("target") == entity["id"]]
    paper_ids: list[str] = []
    for e in inbound:
        prov = e.get("provenance", {})
        paper_ids.append(str(prov.get("paper_id") or e.get("source")))
    # 去重并保持稳定顺序（资产边已排序，此处保序去重即可）。
    seen: set[str] = set()
    unique: list[str] = []
    for pid in paper_ids:
        if pid not in seen:
            seen.add(pid)
            unique.append(pid)
    return {
        "status": "ok" if unique else "empty",
        "query": {"kind": kind, "value": value},
        "data_source": "kg_asset_v1",
        "asset": meta,
        "results": {
            "entity": {"id": entity["id"], "label": entity.get("label"), "properties": entity.get("properties", {})},
            "paper_count": len(unique),
            "papers": unique,
            "provenance_sample": (
                {"paper_id": inbound[0].get("provenance", {}).get("paper_id"),
                 "record_sha256_status": inbound[0].get("provenance", {}).get("record_sha256_status")}
                if inbound else None
            ),
        },
        "unavailable_reason": None,
        "note": HONESTY_NOTE,
    }
