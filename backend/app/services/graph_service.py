"""Serve knowledge-graph data to the API.

Overview graphs come from the pruned exports in ``graphs/*.json``. For a
specific author center, an ego graph is built live from the ``coauthor_edges``
table so the result is not limited to the pruned overview. Keyword/topic center
queries filter the exported graph in memory.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings

GRAPH_DIR = Path(os.getenv("SCISCOPE_GRAPH_DIR", "graphs"))
_FILES = {
    "author": "author_graph.json",
    "keyword": "keyword_graph.json",
    "topic": "paper_topic_graph.json",
}


def is_available() -> bool:
    return any((GRAPH_DIR / name).exists() for name in _FILES.values())


@lru_cache(maxsize=4)
def _load(graph_type: str) -> dict[str, Any]:
    name = _FILES.get(graph_type)
    if not name:
        return {"type": graph_type, "nodes": [], "edges": []}
    path = GRAPH_DIR / name
    if not path.exists():
        return {"type": graph_type, "nodes": [], "edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _ego_filter(graph: dict[str, Any], center: str, limit: int) -> dict[str, Any]:
    edges = [
        e for e in graph.get("edges", [])
        if e.get("source") == center or e.get("target") == center
    ][:limit]
    keep = {center}
    for e in edges:
        keep.add(e["source"])
        keep.add(e["target"])
    nodes = [n for n in graph.get("nodes", []) if n.get("id") in keep or n.get("label") == center]
    return {"type": graph.get("type"), "center": center, "nodes": nodes, "edges": edges}


def _author_ego_from_db(center: str, limit: int) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.db_dsn:
        return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        with psycopg.connect(settings.db_dsn) as conn, conn.cursor() as cur:
            # Resolve the center: accept author_uid or display name.
            cur.execute(
                "SELECT author_uid, name FROM authors WHERE author_uid = %(c)s OR name = %(c)s LIMIT 1",
                {"c": center},
            )
            row = cur.fetchone()
            if not row:
                return None
            center_uid, center_name = row
            cur.execute(
                """
                SELECT ce.author_uid_a, ce.author_uid_b, ce.weight,
                       aa.name AS name_a, ab.name AS name_b
                FROM coauthor_edges ce
                JOIN authors aa ON aa.author_uid = ce.author_uid_a
                JOIN authors ab ON ab.author_uid = ce.author_uid_b
                WHERE ce.author_uid_a = %(u)s OR ce.author_uid_b = %(u)s
                ORDER BY ce.weight DESC
                LIMIT %(lim)s
                """,
                {"u": center_uid, "lim": limit},
            )
            rows = cur.fetchall()
    except Exception:
        return None

    nodes: dict[str, dict[str, Any]] = {center_uid: {"id": center_uid, "label": center_name}}
    edges = []
    for a, b, weight, name_a, name_b in rows:
        nodes.setdefault(a, {"id": a, "label": name_a})
        nodes.setdefault(b, {"id": b, "label": name_b})
        edges.append({"source": a, "target": b, "weight": int(weight)})
    return {"type": "author", "center": center_uid, "nodes": list(nodes.values()), "edges": edges}


def graph(graph_type: str, center: str | None = None, limit: int = 100) -> dict[str, Any]:
    if center and graph_type == "author":
        ego = _author_ego_from_db(center, limit)
        if ego is not None:
            return ego
    full = _load(graph_type)
    if center:
        return _ego_filter(full, center, limit)
    # Overview: cap edges/nodes for payload size; include community themes.
    nodes = full.get("nodes", [])
    edges = full.get("edges", [])[:limit] if limit else full.get("edges", [])
    return {
        "type": full.get("type", graph_type),
        "nodes": nodes,
        "edges": edges,
        "communities": full.get("communities", []),
    }
