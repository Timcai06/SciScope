from __future__ import annotations

import csv
import json
import math
import re
import textwrap
from collections import Counter, defaultdict
from itertools import combinations
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
RECENT_YEAR_START = 2022
RECENT_YEAR_END = 2026


def _format_count(value: int | float) -> str:
    return f"{int(value):,}"


def _year_value(value: Any) -> int | None:
    if str(value or "").isdigit():
        return int(value)
    return None


def _is_recent_year(value: Any) -> bool:
    year = _year_value(value)
    return year is not None and RECENT_YEAR_START <= year <= RECENT_YEAR_END


def _recent_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [paper for paper in papers if _is_recent_year(paper.get("year"))]


def _is_informative_author(name: str) -> bool:
    value = str(name or "").strip()
    if len(value) < 5:
        return False
    if re.match(r"^[A-Z][a-z]+ [A-Z]$", value):
        return False
    if re.search(r"\d", value):
        return False
    return True


def _recent_author_edges(papers: list[dict[str, Any]], *, max_authors: int = 12) -> Counter[tuple[str, str]]:
    return _recent_author_scope(papers, max_authors=max_authors)["edge_counts"]


def _recent_author_scope(papers: list[dict[str, Any]], *, max_authors: int = 12) -> dict[str, Any]:
    edge_counts: Counter[tuple[str, str]] = Counter()
    author_names: set[str] = set()
    valid_papers = 0
    skipped_long = 0
    no_pair = 0
    for paper in _recent_papers(papers):
        authors = [
            str(author).strip()
            for author in paper.get("authors") or []
            if str(author).strip() and _is_informative_author(str(author))
        ]
        authors = sorted(set(authors))
        if len(authors) < 2:
            no_pair += 1
            continue
        if len(authors) > max_authors:
            skipped_long += 1
            continue
        valid_papers += 1
        author_names.update(authors)
        fractional_weight = 1 / math.sqrt(len(authors) - 1)
        for author_a, author_b in combinations(authors, 2):
            edge_counts[(author_a, author_b)] += fractional_weight
    return {
        "edge_counts": edge_counts,
        "authors": author_names,
        "valid_papers": valid_papers,
        "skipped_long": skipped_long,
        "no_pair": no_pair,
    }


def _field_bucket(value: Any) -> str:
    field = str(value or "").lower()
    if any(token in field for token in ("bio", "med", "health", "clinical")):
        return "Biomedicine"
    if any(token in field for token in ("material", "chem", "battery", "energy", "catalyst")):
        return "Materials"
    if any(token in field for token in ("computer", "cs", "artificial", "information")):
        return "Computer Science"
    return "Cross-field"


def _topic_label(keywords: Counter[str], fallback: str) -> str:
    stopwords = {
        "article",
        "humans",
        "female",
        "male",
        "adult",
        "study",
        "method",
        "model",
        "models",
        "computer science",
        "materials science",
        "biomedicine",
    }
    for keyword, _ in keywords.most_common(8):
        normalized = str(keyword).strip().lower()
        if re.match(r"^[a-z]{2}\.[a-z]{2}$", normalized):
            continue
        if len(normalized) >= 4 and normalized not in stopwords:
            return normalized
    return fallback


def _compact_topic(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if " / " in text:
        parts = text.split(" / ")
        return " / ".join(parts[:2])
    words = text.split()
    if len(words) > 3:
        return " ".join(words[:3])
    return text


def _load_papers(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _wrap_label(value: str, width: int = 24) -> str:
    return "\n".join(textwrap.wrap(str(value), width=width, break_long_words=False)) or str(value)


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["figure_id", "file", "report_section", "source_table", "message", "status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _plot_source_records(quality: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = quality.sort_values("records", ascending=True)
    total_records = int(data["records"].sum())
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    ax.barh(data["source"], data["records"], color="0.25", height=0.58)
    ax.set_title(f"Source Record Coverage (n={_format_count(total_records)})")
    ax.set_xlabel("Records")
    ax.grid(axis="x", linestyle="--")
    for index, value in enumerate(data["records"]):
        ax.text(value + max(data["records"]) * 0.01, index, _format_count(value), va="center", fontsize=8)
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

    years = [_year_value(paper.get("year")) for paper in papers]
    counts = Counter(year for year in years if year is not None and RECENT_YEAR_START <= year <= RECENT_YEAR_END)
    ordered_years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))
    values = [counts[year] for year in ordered_years]
    total_recent = sum(values)

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(ordered_years, values, color="black", linewidth=1.5, marker="o", markersize=2.8)
    ax.fill_between(ordered_years, values, color="0.88")
    ax.set_title(
        f"Publication Year Distribution ({RECENT_YEAR_START}-{RECENT_YEAR_END}, n={_format_count(total_recent)})"
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Papers")
    ax.grid(axis="y", linestyle="--")
    ax.set_xticks(ordered_years)
    max_value = max(values) if values else 1
    for year, value in zip(ordered_years, values, strict=False):
        if value:
            ax.text(year, value + max_value * 0.025, _format_count(value), ha="center", va="bottom", fontsize=7)
    save_figure(fig, output_dir / "year_distribution.png")
    return {
        "figure_id": "year_distribution",
        "file": "year_distribution.png",
        "report_section": "文献分布分析",
        "source_table": "papers_clean.json",
        "message": "聚焦近五年有效年份, 过滤历史和未来年份噪声。",
        "status": "final",
    }


def _plot_source_year_heatmap(papers: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    recent = _recent_papers(papers)
    preferred_sources = ["arxiv", "pubmed", "pmc", "crossref", "doaj", "openalex"]
    seen_sources = {str(paper.get("source") or "unknown").lower() for paper in recent}
    sources = [source for source in preferred_sources if source in seen_sources]
    sources.extend(sorted(seen_sources.difference(sources)))
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))
    counts = Counter(
        (str(paper.get("source") or "unknown").lower(), _year_value(paper.get("year")))
        for paper in recent
    )
    matrix = np.array([[counts[(source, year)] for year in years] for source in sources], dtype=float)
    total_recent = int(matrix.sum())

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    image = ax.imshow(matrix, cmap="Greys", aspect="auto")
    ax.set_title(f"Source-Year Coverage ({RECENT_YEAR_START}-{RECENT_YEAR_END}, n={_format_count(total_recent)})")
    ax.set_xticks(range(len(years)), years)
    ax.set_yticks(range(len(sources)), sources)
    max_value = float(matrix.max()) if matrix.size else 0
    threshold = max_value * 0.62
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            value = int(matrix[row_index, col_index])
            color = "white" if value > threshold else "black"
            ax.text(col_index, row_index, _format_count(value), ha="center", va="center", color=color, fontsize=6.5)
    fig.colorbar(image, ax=ax, fraction=0.028, pad=0.02, label="Records")
    save_figure(fig, output_dir / "source_year_heatmap.png")
    return {
        "figure_id": "source_year_heatmap",
        "file": "source_year_heatmap.png",
        "report_section": "文献分布分析",
        "source_table": "papers_clean.json",
        "message": "展示近五年来源-年份覆盖规模, 直接暴露采集年份偏置。",
        "status": "final",
    }


def _plot_top_keywords(keywords: pd.DataFrame, output_dir: Path, *, top_n: int = 15) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keywords.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data = data[(data["year"] >= RECENT_YEAR_START) & (data["year"] <= RECENT_YEAR_END)]
    counts = data["keyword"].dropna().astype(str).value_counts().head(top_n).sort_values(ascending=True)
    labels = [_wrap_label(label, width=28) for label in counts.index]
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    ax.barh(labels, counts.values, color="0.2", height=0.6)
    ax.set_title(f"Top Keywords ({RECENT_YEAR_START}-{RECENT_YEAR_END})")
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
        "message": "呈现近五年样本中的高频研究主题。",
        "status": "final",
    }


def _plot_keyword_year_heatmap(keyword_year: pd.DataFrame, output_dir: Path, *, top_n: int = 12) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keyword_year.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data = data.dropna(subset=["keyword", "year"])
    data["year"] = data["year"].astype(int)
    data = data[(data["year"] >= RECENT_YEAR_START) & (data["year"] <= RECENT_YEAR_END)]
    top_keywords = data.groupby("keyword")["count"].sum().sort_values(ascending=False).head(top_n).index
    data = data[data["keyword"].isin(top_keywords)]
    pivot = data.pivot_table(index="keyword", columns="year", values="count", aggfunc="sum", fill_value=0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=True).index]
    pivot = pivot.reindex(columns=list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1)), fill_value=0)
    normalized = pivot.div(pivot.max(axis=1).replace(0, np.nan), axis=0).fillna(0)

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    image = ax.imshow(normalized.values, cmap="Greys", vmin=0, vmax=1, aspect="auto")
    ax.set_title(f"Keyword Evolution Heatmap ({RECENT_YEAR_START}-{RECENT_YEAR_END})")
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
        "message": "展示近五年高频关键词的年度热度变化, 支撑热点趋势分析。",
        "status": "final",
    }


def _plot_author_communities(
    papers: list[dict[str, Any]],
    output_dir: Path,
    *,
    graph_edges: int = 900,
    communities_per_field: int = 3,
) -> dict[str, str]:
    from matplotlib import pyplot as plt

    scope = _recent_author_scope(papers)
    edge_counts = scope["edge_counts"]
    candidate_edges = len(edge_counts)
    candidate_authors = len(scope["authors"])
    valid_papers = int(scope["valid_papers"])
    graph = nx.Graph()
    for (author_a, author_b), weight in edge_counts.most_common(graph_edges):
        graph.add_edge(author_a, author_b, weight=float(weight))

    communities = (
        list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
        if graph.number_of_edges()
        else []
    )
    author_to_community = {
        author: index
        for index, community in enumerate(communities)
        for author in community
    }

    community_keywords: dict[int, Counter[str]] = defaultdict(Counter)
    community_fields: dict[int, Counter[str]] = defaultdict(Counter)
    community_papers: dict[int, set[str]] = defaultdict(set)
    for paper in _recent_papers(papers):
        authors = {str(author).strip() for author in paper.get("authors") or []}
        community_ids = {author_to_community[author] for author in authors if author in author_to_community}
        if not community_ids:
            continue
        paper_key = str(paper.get("paper_id") or paper.get("title") or id(paper))
        for community_id in community_ids:
            community_papers[community_id].add(paper_key)
            community_fields[community_id][_field_bucket(paper.get("field"))] += 1
            for keyword in paper.get("keywords") or []:
                community_keywords[community_id][str(keyword).strip().lower()] += 1

    rows: list[dict[str, Any]] = []
    for community_id, community in enumerate(communities):
        subgraph = graph.subgraph(community)
        strength = sum(float(data.get("weight") or 0) for _, _, data in subgraph.edges(data=True))
        if strength <= 0:
            continue
        dominant_field = (
            community_fields[community_id].most_common(1)[0][0]
            if community_fields.get(community_id)
            else "Cross-field"
        )
        top_members = sorted(subgraph.degree(weight="weight"), key=lambda item: item[1], reverse=True)[:2]
        fallback = " / ".join(author for author, _ in top_members) or "author community"
        rows.append(
            {
                "community_id": community_id,
                "field": dominant_field,
                "members": len(community),
                "papers": len(community_papers.get(community_id, set())),
                "strength": strength,
                "topic": _topic_label(community_keywords[community_id], fallback),
                "fallback": fallback,
            }
        )

    field_order = ["Computer Science", "Biomedicine", "Materials", "Cross-field"]
    grouped: dict[str, list[dict[str, Any]]] = {field: [] for field in field_order}
    for row in sorted(rows, key=lambda item: (-item["papers"], -item["strength"])):
        bucket = grouped.setdefault(row["field"], [])
        if len(bucket) < communities_per_field:
            bucket.append(row)

    active_fields = [field for field in field_order if grouped.get(field)]
    used_labels: Counter[str] = Counter()

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    shade_by_field = {
        "Computer Science": "white",
        "Biomedicine": "0.82",
        "Materials": "0.62",
        "Cross-field": "0.38",
    }
    for x_index, field in enumerate(active_fields):
        field_rows = grouped.get(field, [])
        for y_index, row in enumerate(field_rows):
            y = (len(field_rows) - y_index) * 1.55
            size = 280 + min(row["papers"], 120) * 7 + min(row["strength"], 40) * 12
            ax.scatter(
                x_index,
                y,
                s=size,
                c=shade_by_field.get(field, "0.75"),
                edgecolors="black",
                linewidths=0.9,
                zorder=3,
            )
            topic = _compact_topic(row["topic"])
            used_labels[topic] += 1
            if used_labels[topic] > 1:
                topic = _compact_topic(row["fallback"])
            label = f"{_wrap_label(topic, width=15)}\n{row['members']} authors / {row['papers']} papers"
            ax.text(x_index, y, label, ha="center", va="center", fontsize=5.7, zorder=4)
    ax.set_title(
        f"Author Collaboration Communities ({RECENT_YEAR_START}-{RECENT_YEAR_END}, "
        f"core {min(graph_edges, candidate_edges):,}/{candidate_edges:,} edges)"
    )
    ax.set_xticks(range(len(active_fields)), active_fields)
    ax.set_yticks([])
    ax.grid(axis="x", linestyle="--", color="0.86")
    ax.set_xlim(-0.6, max(len(active_fields) - 0.4, 0.6))
    max_rows = max((len(items) for items in grouped.values()), default=1)
    ax.set_ylim(0.3, max_rows * 1.55 + 0.9)
    ax.set_xlabel("Dominant Community Field")
    ax.text(
        0.01,
        0.015,
        f"Scope: {valid_papers:,} papers, {candidate_authors:,} authors, {candidate_edges:,} weighted coauthor edges.",
        transform=ax.transAxes,
        fontsize=6.8,
        color="0.25",
    )
    save_figure(fig, output_dir / "author_collaboration_network.png")
    return {
        "figure_id": "author_communities",
        "file": "author_collaboration_network.png",
        "report_section": "作者合作网络分析",
        "source_table": "papers_clean.json",
        "message": "将近五年合作网络聚合为主题社区气泡, 避免静态全量网络不可读。",
        "status": "final",
    }


def _plot_top_author_collaborations(papers: list[dict[str, Any]], output_dir: Path, *, top_n: int = 12) -> dict[str, str]:
    from matplotlib import pyplot as plt

    edge_counts = _recent_author_edges(papers)
    candidate_edges = len(edge_counts)
    top_edges = edge_counts.most_common(top_n)
    labels = [_wrap_label(f"{author_a} / {author_b}", width=32) for (author_a, author_b), _ in top_edges]
    values = [weight for _, weight in top_edges]

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    positions = np.arange(len(labels))
    ax.barh(positions, values, color="0.22", height=0.58)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Fractional Collaboration Weight")
    ax.set_title(
        f"Top Repeated Author Collaborations "
        f"(top {len(top_edges)}/{_format_count(candidate_edges)} weighted edges)"
    )
    ax.grid(axis="x", linestyle="--")
    max_value = max(values) if values else 1
    for position, value in zip(positions, values, strict=False):
        ax.text(value + max_value * 0.015, position, f"{value:.1f}", va="center", fontsize=7)
    save_figure(fig, output_dir / "top_author_collaborations.png")
    return {
        "figure_id": "top_author_collaborations",
        "file": "top_author_collaborations.png",
        "report_section": "作者合作网络分析",
        "source_table": "papers_clean.json",
        "message": "列出近五年重复出现的高权重作者合作关系, 解释合作边权来源。",
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

    manifest: list[dict[str, str]] = []
    if not quality.empty:
        manifest.append(_plot_source_records(quality, output_path))
        manifest.append(_plot_quality_matrix(quality, output_path))
        manifest.append(_plot_text_coverage(quality, output_path))
    if papers:
        manifest.append(_plot_year_distribution(papers, output_path))
        manifest.append(_plot_source_year_heatmap(papers, output_path))
    if not keywords.empty:
        manifest.append(_plot_top_keywords(keywords, output_path))
    if not keyword_year.empty:
        manifest.append(_plot_keyword_year_heatmap(keyword_year, output_path))
    if papers:
        manifest.append(_plot_author_communities(papers, output_path))
        manifest.append(_plot_top_author_collaborations(papers, output_path))

    _write_manifest(output_path / "figure_manifest.csv", manifest)
    return {
        "figures": len(manifest),
        "analysis_dir": str(analysis_path),
        "output_dir": str(output_path),
        "manifest": str(output_path / "figure_manifest.csv"),
    }
