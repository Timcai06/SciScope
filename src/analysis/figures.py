from __future__ import annotations

import csv
import json
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from src.analysis.plotting import configure_plot_style, save_figure


QUALITY_FIELDS = [
    ("title_count", "Title"),
    ("abstract_count", "Abstract"),
    ("authors_count", "Authors"),
    ("year_count", "Year"),
    ("keywords_count", "Keywords"),
    ("full_text_count", "Full text"),
]


def _load_papers(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _wrap_label(value: str, width: int = 24) -> str:
    return "\n".join(textwrap.wrap(str(value), width=width, break_long_words=False)) or str(value)


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["figure_id", "file", "report_section", "source_table", "message", "status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _plot_source_records(quality: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = quality.sort_values("records", ascending=True)
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    ax.barh(data["source"], data["records"], color="0.25", height=0.58)
    ax.set_title("Source Record Coverage")
    ax.set_xlabel("Records")
    ax.grid(axis="x", linestyle="--")
    for index, value in enumerate(data["records"]):
        ax.text(value + max(data["records"]) * 0.01, index, str(int(value)), va="center", fontsize=8)
    save_figure(fig, output_dir / "source_records_bar.png")
    return {
        "figure_id": "source_records",
        "file": "source_records_bar.png",
        "report_section": "数据底座与采集状态",
        "source_table": "source_quality_report.csv",
        "message": "展示当前六个公开来源的基线采集规模。",
        "status": "final",
    }


def _plot_quality_matrix(quality: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = quality.sort_values("source").reset_index(drop=True)
    matrix = np.zeros((len(data), len(QUALITY_FIELDS)))
    for col_index, (column, _) in enumerate(QUALITY_FIELDS):
        matrix[:, col_index] = data[column].astype(float) / data["records"].replace(0, np.nan).astype(float)
    matrix = np.nan_to_num(matrix)

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    image = ax.imshow(matrix, cmap="Greys", vmin=0, vmax=1, aspect="auto")
    ax.set_title("Field Completeness by Source")
    ax.set_xticks(range(len(QUALITY_FIELDS)), [label for _, label in QUALITY_FIELDS], rotation=30, ha="right")
    ax.set_yticks(range(len(data)), data["source"])
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            value = matrix[row_index, col_index]
            color = "white" if value > 0.62 else "black"
            ax.text(col_index, row_index, f"{value:.0%}", ha="center", va="center", color=color, fontsize=7)
    fig.colorbar(image, ax=ax, fraction=0.028, pad=0.02, label="Completeness")
    save_figure(fig, output_dir / "source_quality_matrix.png")
    return {
        "figure_id": "source_quality",
        "file": "source_quality_matrix.png",
        "report_section": "数据底座与采集状态",
        "source_table": "source_quality_report.csv",
        "message": "比较各来源关键字段完整度, 支撑数据可信度说明。",
        "status": "final",
    }


def _plot_year_distribution(papers: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    years = [int(paper["year"]) for paper in papers if str(paper.get("year") or "").isdigit()]
    counts = Counter(year for year in years if 1900 <= year <= 2026)
    ordered_years = sorted(counts)
    values = [counts[year] for year in ordered_years]

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(ordered_years, values, color="black", linewidth=1.5, marker="o", markersize=2.8)
    ax.fill_between(ordered_years, values, color="0.88")
    ax.set_title("Publication Year Distribution")
    ax.set_xlabel("Year")
    ax.set_ylabel("Papers")
    ax.grid(axis="y", linestyle="--")
    if ordered_years:
        tick_step = max(1, len(ordered_years) // 10)
        ax.set_xticks(ordered_years[::tick_step])
        ax.tick_params(axis="x", rotation=35)
    save_figure(fig, output_dir / "year_distribution.png")
    return {
        "figure_id": "year_distribution",
        "file": "year_distribution.png",
        "report_section": "文献分布分析",
        "source_table": "papers_clean.json",
        "message": "展示样本文献的年份覆盖和增长轮廓。",
        "status": "final",
    }


def _plot_top_keywords(keywords: pd.DataFrame, output_dir: Path, *, top_n: int = 15) -> dict[str, str]:
    from matplotlib import pyplot as plt

    counts = keywords["keyword"].dropna().astype(str).value_counts().head(top_n).sort_values(ascending=True)
    labels = [_wrap_label(label, width=28) for label in counts.index]
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    ax.barh(labels, counts.values, color="0.2", height=0.6)
    ax.set_title("Top Keywords")
    ax.set_xlabel("Papers")
    ax.grid(axis="x", linestyle="--")
    for index, value in enumerate(counts.values):
        ax.text(value + max(counts.values) * 0.01, index, str(int(value)), va="center", fontsize=7)
    save_figure(fig, output_dir / "top_keywords.png")
    return {
        "figure_id": "top_keywords",
        "file": "top_keywords.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "paper_keywords.csv",
        "message": "呈现当前样本中的高频研究主题。",
        "status": "final",
    }


def _plot_keyword_year_heatmap(keyword_year: pd.DataFrame, output_dir: Path, *, top_n: int = 12) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keyword_year.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data = data.dropna(subset=["keyword", "year"])
    data["year"] = data["year"].astype(int)
    top_keywords = data.groupby("keyword")["count"].sum().sort_values(ascending=False).head(top_n).index
    data = data[data["keyword"].isin(top_keywords)]
    pivot = data.pivot_table(index="keyword", columns="year", values="count", aggfunc="sum", fill_value=0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=True).index]
    if len(pivot.columns) > 14:
        recent_years = sorted(pivot.columns)[-14:]
        pivot = pivot[recent_years]
    normalized = pivot.div(pivot.max(axis=1).replace(0, np.nan), axis=0).fillna(0)

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    image = ax.imshow(normalized.values, cmap="Greys", vmin=0, vmax=1, aspect="auto")
    ax.set_title("Keyword Evolution Heatmap")
    ax.set_xticks(range(len(normalized.columns)), normalized.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(normalized.index)), [_wrap_label(item, width=24) for item in normalized.index])
    for row_index in range(normalized.shape[0]):
        for col_index in range(normalized.shape[1]):
            value = int(pivot.iloc[row_index, col_index])
            if value:
                color = "white" if normalized.iloc[row_index, col_index] > 0.62 else "black"
                ax.text(col_index, row_index, str(value), ha="center", va="center", color=color, fontsize=6)
    fig.colorbar(image, ax=ax, fraction=0.028, pad=0.02, label="Row-normalized heat")
    save_figure(fig, output_dir / "keyword_evolution_heatmap.png")
    return {
        "figure_id": "keyword_evolution",
        "file": "keyword_evolution_heatmap.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "keyword_year_matrix.csv",
        "message": "展示高频关键词的年度热度变化, 支撑热点趋势分析。",
        "status": "final",
    }


def _plot_author_network(edges: pd.DataFrame, output_dir: Path, *, top_edges: int = 28) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = edges.sort_values("weight", ascending=False).head(top_edges)
    graph = nx.Graph()
    for row in data.itertuples(index=False):
        graph.add_edge(str(row.author_a), str(row.author_b), weight=float(row.weight))
    if graph.number_of_nodes() > 0 and not nx.is_connected(graph):
        largest_nodes = max(nx.connected_components(graph), key=len)
        graph = graph.subgraph(largest_nodes).copy()

    fig, ax = plt.subplots(figsize=(7.4, 5.1))
    if graph.number_of_nodes() > 0:
        pos = nx.spring_layout(graph, seed=42, weight="weight", k=0.95, iterations=120)
        weighted_degree = dict(graph.degree(weight="weight"))
        sizes = [120 + weighted_degree[node] * 45 for node in graph.nodes]
        widths = [0.6 + graph.edges[edge]["weight"] * 0.35 for edge in graph.edges]
        nx.draw_networkx_edges(graph, pos, ax=ax, width=widths, edge_color="0.55")
        nx.draw_networkx_nodes(graph, pos, ax=ax, node_size=sizes, node_color="white", edgecolors="black", linewidths=0.9)
        top_label_nodes = {node for node, _ in sorted(weighted_degree.items(), key=lambda item: item[1], reverse=True)[:7]}
        labels = {node: _wrap_label(node, width=16) for node in top_label_nodes}
        nx.draw_networkx_labels(
            graph,
            pos,
            labels=labels,
            ax=ax,
            font_size=6,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.2},
        )
        ax.margins(0.18)
        ax.set_aspect("equal")
    ax.set_title("Author Collaboration Network")
    ax.axis("off")
    save_figure(fig, output_dir / "author_collaboration_network.png")
    return {
        "figure_id": "author_collaboration",
        "file": "author_collaboration_network.png",
        "report_section": "作者合作网络分析",
        "source_table": "author_collaboration_edges.csv",
        "message": "展示高权重合作关系形成的核心作者网络。",
        "status": "final",
    }


def _plot_text_coverage(quality: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = quality.sort_values("source")
    abstract_rate = data["abstract_count"].astype(float) / data["records"].replace(0, np.nan).astype(float)
    full_text_rate = data["full_text_count"].astype(float) / data["records"].replace(0, np.nan).astype(float)
    x = np.arange(len(data))
    width = 0.34

    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    ax.bar(x - width / 2, abstract_rate.fillna(0), width, label="Abstract", color="0.25")
    ax.bar(x + width / 2, full_text_rate.fillna(0), width, label="Full text", color="0.72", edgecolor="black", linewidth=0.5)
    ax.set_title("Abstract and Full-text Coverage")
    ax.set_ylabel("Coverage")
    ax.set_ylim(0, 1.08)
    ax.set_xticks(x, data["source"], rotation=25, ha="right")
    ax.set_yticks(np.linspace(0, 1, 6), [f"{int(value * 100)}%" for value in np.linspace(0, 1, 6)])
    ax.grid(axis="y", linestyle="--")
    ax.legend(loc="upper right")
    save_figure(fig, output_dir / "abstract_fulltext_coverage.png")
    return {
        "figure_id": "text_coverage",
        "file": "abstract_fulltext_coverage.png",
        "report_section": "数据质量与可信度审计",
        "source_table": "source_quality_report.csv",
        "message": "区分摘要级分析和全文级 RAG 的证据边界。",
        "status": "final",
    }


def build_report_figures(
    *,
    analysis_dir: str | Path = "data/analysis",
    output_dir: str | Path = "output/assets/sciscope_data_report",
) -> dict[str, Any]:
    configure_plot_style()
    analysis_path = Path(analysis_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    papers = _load_papers(analysis_path / "papers_clean.json")
    quality = _read_csv(analysis_path / "source_quality_report.csv")
    keywords = _read_csv(analysis_path / "paper_keywords.csv")
    keyword_year = _read_csv(analysis_path / "keyword_year_matrix.csv")
    edges = _read_csv(analysis_path / "author_collaboration_edges.csv")

    manifest: list[dict[str, str]] = []
    if not quality.empty:
        manifest.append(_plot_source_records(quality, output_path))
        manifest.append(_plot_quality_matrix(quality, output_path))
        manifest.append(_plot_text_coverage(quality, output_path))
    if papers:
        manifest.append(_plot_year_distribution(papers, output_path))
    if not keywords.empty:
        manifest.append(_plot_top_keywords(keywords, output_path))
    if not keyword_year.empty:
        manifest.append(_plot_keyword_year_heatmap(keyword_year, output_path))
    if not edges.empty:
        manifest.append(_plot_author_network(edges, output_path))

    _write_manifest(output_path / "figure_manifest.csv", manifest)
    return {
        "figures": len(manifest),
        "analysis_dir": str(analysis_path),
        "output_dir": str(output_path),
        "manifest": str(output_path / "figure_manifest.csv"),
    }
