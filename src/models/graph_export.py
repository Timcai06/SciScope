"""Export frontend-friendly knowledge-graph JSON from the analysis assets.

Produces pruned overview graphs (top nodes by centrality + the edges among
them) so the frontend can render force-directed views without loading the full
multi-million-edge tables. The full edges remain queryable per-entity from the
service layer (coauthor_edges in PostgreSQL) for ego-graph requests.

Outputs (the deliverable "graph files"):
    graphs/author_graph.json
    graphs/keyword_graph.json
    graphs/paper_topic_graph.json
    graphs/graph_metrics.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.models.keyword_filter import is_noise_keyword

ANALYSIS_DIR = Path("data/analysis")
OUTPUT_DIR = Path("graphs")
TOP_AUTHORS = 300
TOP_KEYWORDS = 300
MIN_AUTHOR_EDGE_WEIGHT = 2
EDGE_CHUNK = 500_000


def _safe(value: Any) -> Any:
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def _stream_edges_within(
    path: Path, a_col: str, b_col: str, weight_col: str, allowed: set[str], min_weight: int
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    if not path.exists():
        return edges
    for chunk in pd.read_csv(path, usecols=[a_col, b_col, weight_col], chunksize=EDGE_CHUNK):
        mask = chunk[a_col].isin(allowed) & chunk[b_col].isin(allowed) & (chunk[weight_col] >= min_weight)
        for _, row in chunk[mask].iterrows():
            edges.append(
                {"source": str(row[a_col]), "target": str(row[b_col]), "weight": int(row[weight_col])}
            )
    return edges


def build_author_graph(analysis_dir: Path) -> dict[str, Any]:
    metrics = pd.read_csv(
        analysis_dir / "author_metrics.csv",
        usecols=["author_key", "author", "paper_count", "weighted_degree", "pagerank", "community_id", "dominant_field"],
    )
    top = metrics.sort_values("weighted_degree", ascending=False).head(TOP_AUTHORS)
    allowed = set(top["author_key"].astype(str))
    nodes = [
        {
            "id": str(r.author_key),
            "label": _safe(r.author),
            "paper_count": int(r.paper_count or 0),
            "weighted_degree": float(r.weighted_degree or 0),
            "pagerank": float(r.pagerank or 0),
            "community": _safe(r.community_id),
            "field": _safe(r.dominant_field),
        }
        for r in top.itertuples()
    ]
    edges = _stream_edges_within(
        analysis_dir / "author_collaboration_edges.csv",
        "author_a_key", "author_b_key", "weight", allowed, MIN_AUTHOR_EDGE_WEIGHT,
    )
    return {"type": "author", "nodes": nodes, "edges": edges}


def _community_summaries(nodes: list[dict[str, Any]], top_k: int = 8) -> list[dict[str, Any]]:
    """Turn raw community ids into interpretable research-theme summaries.

    Groups nodes by community and lists each community's most central members, so
    a numeric community id becomes a readable theme (e.g. {LLM, RAG, transformer}).
    """
    from collections import defaultdict

    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        cid = node.get("community")
        if cid is not None:
            groups[cid].append(node)
    summaries = []
    for cid, members in groups.items():
        members.sort(key=lambda n: n.get("pagerank", 0) or 0, reverse=True)
        summaries.append(
            {
                "community": _safe(cid),
                "size": len(members),
                "top_terms": [m["label"] for m in members[:top_k]],
            }
        )
    summaries.sort(key=lambda s: s["size"], reverse=True)
    return summaries


def build_keyword_graph(analysis_dir: Path) -> dict[str, Any]:
    metrics = pd.read_csv(
        analysis_dir / "keyword_metrics.csv",
        usecols=["keyword", "doc_count", "pagerank", "community_id", "lifecycle_stage"],
    )
    metrics = metrics[~metrics["keyword"].astype(str).map(is_noise_keyword)]
    top = metrics.sort_values("pagerank", ascending=False).head(TOP_KEYWORDS)
    allowed = set(top["keyword"].astype(str))
    nodes = [
        {
            "id": str(r.keyword),
            "label": str(r.keyword),
            "doc_count": int(r.doc_count or 0),
            "pagerank": float(r.pagerank or 0),
            "community": _safe(r.community_id),
            "lifecycle": _safe(r.lifecycle_stage),
        }
        for r in top.itertuples()
    ]
    edges = _stream_edges_within(
        analysis_dir / "keyword_cooccurrence_edges.csv",
        "keyword_a", "keyword_b", "weight", allowed, 1,
    )
    return {"type": "keyword", "nodes": nodes, "edges": edges, "communities": _community_summaries(nodes)}


def build_paper_topic_graph(analysis_dir: Path) -> dict[str, Any]:
    topic_kw = pd.read_csv(analysis_dir / "topic_keywords.csv")
    share = pd.read_csv(analysis_dir / "topic_year_share.csv")
    # Use the model with the most topics for a richer view.
    model = topic_kw["model"].value_counts().idxmax()
    topic_kw = topic_kw[topic_kw["model"] == model]
    sizes = share[share["model"] == model].groupby("topic_id")["paper_count"].sum().to_dict()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_keywords: set[str] = set()
    for r in topic_kw.itertuples():
        topic_node = f"topic:{r.topic_id}"
        nodes.append(
            {
                "id": topic_node,
                "label": f"Topic {r.topic_id}",
                "kind": "topic",
                "paper_count": int(sizes.get(r.topic_id, 0)),
            }
        )
        keywords = [k.strip() for k in str(r.ranked_keywords).split(";") if k.strip()][:8]
        for kw in keywords:
            kw_node = f"kw:{kw}"
            if kw not in seen_keywords:
                nodes.append({"id": kw_node, "label": kw, "kind": "keyword"})
                seen_keywords.add(kw)
            edges.append({"source": topic_node, "target": kw_node, "weight": 1})
    return {"type": "paper_topic", "model": str(model), "nodes": nodes, "edges": edges}


def run(analysis_dir: Path = ANALYSIS_DIR, output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    author = build_author_graph(analysis_dir)
    keyword = build_keyword_graph(analysis_dir)
    topic = build_paper_topic_graph(analysis_dir)

    (output_dir / "author_graph.json").write_text(json.dumps(author, ensure_ascii=False), encoding="utf-8")
    (output_dir / "keyword_graph.json").write_text(json.dumps(keyword, ensure_ascii=False), encoding="utf-8")
    (output_dir / "paper_topic_graph.json").write_text(json.dumps(topic, ensure_ascii=False), encoding="utf-8")

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "author": {"nodes": len(author["nodes"]), "edges": len(author["edges"]), "top_n": TOP_AUTHORS},
        "keyword": {"nodes": len(keyword["nodes"]), "edges": len(keyword["edges"]), "top_n": TOP_KEYWORDS,
                    "communities": len(keyword.get("communities", []))},
        "paper_topic": {"nodes": len(topic["nodes"]), "edges": len(topic["edges"]), "model": topic["model"]},
        "note": "Overview graphs are pruned to top-centrality nodes; per-author ego graphs are served live from coauthor_edges.",
    }
    (output_dir / "graph_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SciScope knowledge-graph JSON")
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.analysis_dir, args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
