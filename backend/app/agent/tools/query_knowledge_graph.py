"""query_knowledge_graph — research communities / author-keyword-topic graphs.

G02 起，知识图谱查询优先消费 G01 的 ``knowledge-graph-asset/v1`` 资产
（``backend/app/services/kg_asset_service``），返回带 schema_version /
input_fingerprint / 关系类型 / provenance 与哈希状态的结构化响应。

数据源切换是显式的（不静默）：
- community / author：资产不含概览社区与作者实体，仍走旧 graph_service
  （``data_source="legacy_graph_export"``）；
- keyword/topic：资产可用 → ``kg_asset_v1``；资产不可用 → 降级旧 keyword 图，
  并在响应中写明降级原因；
- paper / source / year：仅资产提供等价查询；资产不可用 → 结构化
  ``unavailable``（旧路径无等价物，宁可不可用也不换源伪装）。
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.tools.base import Tool
from backend.app.services import graph_service, kg_asset_service

SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_knowledge_graph",
        "description": (
            "查询知识图谱。type=community 返回研究社区主题;"
            "type=author 返回作者 ego 图;"
            "type=keyword/topic 返回关键词/主题相关论文(优先 G01 资产);"
            "type=paper/source/year 返回实体邻居与来源论文(仅 G01 资产)。"
            "center 可选。返回的关系仅为来源/关键词/年份等已有字段关系,不是因果结论。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "community / author / keyword / topic / paper / source / year"},
                "center": {"type": "string", "description": "中心实体(作者名/关键词/paper_id/source/year),可选"},
            },
            "required": ["type"],
        },
    },
}


def _legacy_response(center: str, data: dict[str, Any], reason: str | None = None) -> str:
    """旧路径响应：统一三态 status，显式标注 data_source 与降级原因。

    - 旧图谱导出不存在（``graph_service.is_available()`` 为 False）→ unavailable，
      reason 固定 ``legacy_graph_export_unavailable``，绝不伪装成可用；
    - 旧图谱存在但中心无结果 → empty；
    - 有结果 → ok。
    """
    if not graph_service.is_available():
        status, unavailable_reason = "unavailable", "legacy_graph_export_unavailable"
    elif not data.get("nodes") and not data.get("edges"):
        status, unavailable_reason = "empty", None
    else:
        status, unavailable_reason = "ok", None
    return json.dumps(
        {
            "status": status,
            "unavailable_reason": unavailable_reason,
            "data_source": "legacy_graph_export",
            "query": {"type": data.get("type"), "center": center},
            "node_count": len(data.get("nodes", [])),
            "edge_count": len(data.get("edges", [])),
            "nodes": [n.get("label") for n in data.get("nodes", [])][:20],
            "degraded_reason": reason,
            "note": "旧图谱导出路径（output/graphs），关系为概览图共现/中心性；如需可审计字段关系请使用 G01 资产。",
        },
        ensure_ascii=False,
    )


def run(args: dict[str, Any]) -> str:
    gtype = str(args.get("type") or "keyword").strip().lower()
    center = (args.get("center") or "").strip() or None

    # community / author：资产不提供，走旧路径（明确标注）。
    if gtype in ("community", "communities", "社区"):
        if not graph_service.is_available():
            return json.dumps(
                {"status": "unavailable", "unavailable_reason": "legacy_graph_export_unavailable",
                 "data_source": "legacy_graph_export", "results": []},
                ensure_ascii=False,
            )
        data = graph_service.graph("keyword", limit=1)
        comms = data.get("communities", [])[:8]
        if not comms:
            return json.dumps(
                {"data_source": "legacy_graph_export", "status": "empty",
                 "unavailable_reason": None, "reason": "旧图谱导出无社区数据", "results": []},
                ensure_ascii=False,
            )
        return json.dumps(
            {"data_source": "legacy_graph_export", "status": "ok",
             "unavailable_reason": None,
             "results": [{"size": c["size"], "top_terms": c["top_terms"][:8]} for c in comms]},
            ensure_ascii=False,
        )
    if gtype == "author":
        data = graph_service.graph("author", center=center, limit=20)
        return _legacy_response(center or "", data)

    # 资产可消费类型：keyword/topic → 资产 topic；paper/source/year 直查资产。
    asset_kind = {"topic": "topic", "keyword": "topic", "paper": "paper", "source": "source", "year": "year"}.get(gtype)
    if asset_kind:
        resp = kg_asset_service.query(asset_kind, center or "")
        if resp["status"] == "ok" or resp["status"] == "empty":
            return json.dumps(resp, ensure_ascii=False)
        # 资产不可用。
        reason = resp.get("unavailable_reason") or "kg_asset_unavailable"
        if asset_kind == "topic":
            # keyword/topic 可安全降级到旧 keyword 图（响应中写明原因，不静默）。
            legacy_type = "keyword"
            data = graph_service.graph(legacy_type, center=center, limit=20)
            return _legacy_response(center or "", data, reason=f"kg_asset_unavailable:{reason}")
        # paper/source/year：旧路径无等价查询 → 结构化 unavailable，不换源伪装。
        return json.dumps(
            {
                "status": "unavailable",
                "query": {"type": gtype, "center": center},
                "data_source": None,
                "asset": None,
                "results": [],
                "unavailable_reason": f"kg_asset_unavailable:{reason}",
                "note": kg_asset_service.HONESTY_NOTE,
            },
            ensure_ascii=False,
        )

    # 未知类型：结构化 unavailable，不抛异常。
    return json.dumps(
        {
            "status": "unavailable",
            "query": {"type": gtype, "center": center},
            "results": [],
            "unavailable_reason": f"unsupported_kind:{gtype}",
            "note": kg_asset_service.HONESTY_NOTE,
        },
        ensure_ascii=False,
    )


TOOL = Tool(
    name="query_knowledge_graph",
    schema=SCHEMA,
    run=run,
    prompt_fragment="查知识图谱/研究社区(作者/关键词/主题/论文/来源/年份)",
)
