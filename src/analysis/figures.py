from __future__ import annotations

"""Render report figures from analysis assets and emit an ingestion manifest."""

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
from matplotlib.colors import LinearSegmentedColormap

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
REPRESENTATIVE_TREND_KEYWORDS = [
    "large language model",
    "retrieval augmented generation",
    "prompt engineering",
    "vision language model",
    "knowledge graph",
    "graph neural network",
    "materials informatics",
    "drug discovery",
]
BLACK = "#000000"
CHARCOAL = "#2a272a"
GRAPHITE = "#4b4a54"
STEEL = "#677381"
BLUEGREY = "#82a0aa"
MINTGREY = "#a3cfcd"
FILL_DARK = GRAPHITE
FILL_MEDIUM = STEEL
FILL_SOFT = BLUEGREY
FILL_LIGHT = MINTGREY
PURPLE = CHARCOAL
BROWN = CHARCOAL
BLUE = GRAPHITE
PURPLE_LIGHT = MINTGREY
BROWN_LIGHT = BLUEGREY
BLUE_LIGHT = STEEL
INK = CHARCOAL
MUTED = STEEL
SOURCE_COLORS = {
    "openalex": CHARCOAL,
    "arxiv": GRAPHITE,
    "pubmed": STEEL,
    "pmc": BLUEGREY,
    "crossref": MINTGREY,
    "doaj": FILL_DARK,
}
FIELD_COLORS = {
    "Computer Science": GRAPHITE,
    "Biomedicine": STEEL,
    "Materials": BLUEGREY,
    "Cross-field": MINTGREY,
}
BUBBLE_FIELD_COLORS = {
    "Computer Science": MINTGREY,
    "Biomedicine": BLUEGREY,
    "Materials": MINTGREY,
    "Cross-field": BLUEGREY,
}
SERIES_COLORS = [CHARCOAL, GRAPHITE, STEEL, BLUEGREY, MINTGREY]
COMMUNITY_PALETTE = [GRAPHITE, STEEL, BLUEGREY, MINTGREY, "#735f4b", "#4c7c6f", "#816b8d", CHARCOAL]
LIFECYCLE_COLORS = {
    "emergence": MINTGREY,
    "growth": BLUEGREY,
    "maturity": STEEL,
    "decline": GRAPHITE,
}


def _single_color_cmap(name: str, color: str) -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(name, ["#ffffff", color])


def _format_count(value: int | float) -> str:
    return f"{int(value):,}"


def _community_color(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "unknown" or text == "nan":
        return MUTED
    try:
        return COMMUNITY_PALETTE[int(float(text)) % len(COMMUNITY_PALETTE)]
    except ValueError:
        index = sum(ord(char) for char in text) % len(COMMUNITY_PALETTE)
        return COMMUNITY_PALETTE[index]


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


def _contest_field_label(paper: dict[str, Any]) -> str:
    field = str(paper.get("field_seed") or paper.get("field") or "").lower()
    if "bio" in field or "med" in field:
        return "Biomedicine"
    if "material" in field:
        return "Materials"
    if "computer" in field or "cs" in field or "artificial" in field:
        return "Computer Science"
    return _field_bucket(paper.get("field"))


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


# Report-specific stopwords on top of the shared noise filter (generic single
# words that are not category codes / venues but are still uninformative here).
_REPORT_EXTRA_STOPWORDS = {
    "article", "humans", "study", "models", "studies", "result", "results",
    "approach", "paper", "review", "application", "applications", "based",
}


def _is_report_keyword(value: Any) -> bool:
    """True if the keyword should appear in report charts.

    Delegates noise detection to the shared filter (category codes, generic
    discipline labels, journal/venue names) so report, trend, and graph outputs
    stay consistent, plus a few report-specific generic stopwords.
    """
    from src.models.keyword_filter import is_noise_keyword

    keyword = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if len(keyword) < 4:
        return False
    if keyword in _REPORT_EXTRA_STOPWORDS:
        return False
    if is_noise_keyword(keyword):
        return False
    return True


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
    colors = [SOURCE_COLORS.get(str(source).lower(), MUTED) for source in data["source"]]
    ax.barh(data["source"], data["records"], color=colors, height=0.58)
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
    image = ax.imshow(matrix, cmap=_single_color_cmap("purple_completeness", PURPLE), vmin=0, vmax=1, aspect="auto")
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
    total_records = len(papers)

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(ordered_years, values, color=CHARCOAL, linewidth=1.8, marker="o", markersize=3.2)
    ax.fill_between(ordered_years, values, color=GRAPHITE, alpha=0.22)
    ax.set_title(
        f"Publication Years ({RECENT_YEAR_START}-{RECENT_YEAR_END}: "
        f"{_format_count(total_recent)} / {_format_count(total_records)} records)"
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
    total_records = len(papers)
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
    image = ax.imshow(matrix, cmap=_single_color_cmap("blue_source_year", BLUE), aspect="auto")
    ax.set_title(
        f"Source-Year Coverage ({RECENT_YEAR_START}-{RECENT_YEAR_END}: "
        f"{_format_count(total_recent)} / {_format_count(total_records)} records)"
    )
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


def _plot_field_distribution(papers: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    field_order = ["Computer Science", "Biomedicine", "Materials", "Cross-field"]
    counts = Counter(_contest_field_label(paper) for paper in papers)
    rows = [(field, counts[field]) for field in field_order if counts[field]]
    rows.extend(sorted((field, count) for field, count in counts.items() if field not in field_order))
    rows = sorted(rows, key=lambda item: item[1], reverse=True)
    labels = [field for field, _ in rows]
    values = [count for _, count in rows]
    total = sum(values)

    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    positions = np.arange(len(labels))
    colors = [FIELD_COLORS.get(label, MUTED) for label in labels]
    ax.barh(positions, values, color=colors, edgecolor="white", linewidth=0.8)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Records")
    ax.set_title(f"Contest Field Distribution (n={_format_count(total)})")
    ax.grid(axis="x", linestyle="--")
    max_value = max(values) if values else 1
    ax.set_xlim(0, max_value * 1.22)
    for position, value in zip(positions, values, strict=False):
        percent = value / total if total else 0
        ax.text(value + max_value * 0.012, position, f"{_format_count(value)} / {percent:.1%}", va="center", fontsize=7)
    save_figure(fig, output_dir / "field_distribution.png")
    return {
        "figure_id": "field_distribution",
        "file": "field_distribution.png",
        "report_section": "文献分布分析",
        "source_table": "papers_clean.json",
        "message": "按赛题三大领域口径展示当前语料结构。",
        "status": "final",
    }


def _plot_field_year_heatmap(papers: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    field_order = ["Computer Science", "Biomedicine", "Materials", "Cross-field"]
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))
    recent = _recent_papers(papers)
    total_records = len(papers)
    counts = Counter((_contest_field_label(paper), _year_value(paper.get("year"))) for paper in recent)
    fields = [field for field in field_order if any(counts[(field, year)] for year in years)]
    matrix = np.array([[counts[(field, year)] for year in years] for field in fields], dtype=float)
    total = int(matrix.sum())

    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    image = ax.imshow(matrix, cmap=_single_color_cmap("brown_field_year", BROWN), aspect="auto")
    ax.set_title(
        f"Field-Year Coverage ({RECENT_YEAR_START}-{RECENT_YEAR_END}: "
        f"{_format_count(total)} / {_format_count(total_records)} records)"
    )
    ax.set_xticks(range(len(years)), years)
    ax.set_yticks(range(len(fields)), fields)
    max_value = float(matrix.max()) if matrix.size else 0
    threshold = max_value * 0.62
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            value = int(matrix[row_index, col_index])
            color = "white" if value > threshold else "black"
            ax.text(col_index, row_index, _format_count(value), ha="center", va="center", color=color, fontsize=7)
    fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02, label="Records")
    save_figure(fig, output_dir / "field_year_heatmap.png")
    return {
        "figure_id": "field_year_heatmap",
        "file": "field_year_heatmap.png",
        "report_section": "文献分布分析",
        "source_table": "papers_clean.json",
        "message": "展示计算机、生物医学、材料科学在近五年窗口内的年度覆盖。",
        "status": "final",
    }


def _plot_top_keywords(keywords: pd.DataFrame, output_dir: Path, *, top_n: int = 15) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keywords.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data = data[(data["year"] >= RECENT_YEAR_START) & (data["year"] <= RECENT_YEAR_END)]
    data = data[data["keyword"].map(_is_report_keyword)]
    if "paper_id" in data.columns:
        data = data.drop_duplicates(subset=["paper_id", "keyword"])
    counts = data["keyword"].dropna().astype(str).value_counts().head(top_n).sort_values(ascending=True)
    labels = [_wrap_label(label, width=28) for label in counts.index]
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    colors = [SERIES_COLORS[index % len(SERIES_COLORS)] for index in range(len(labels))]
    ax.barh(labels, counts.values, color=colors, height=0.6)
    ax.set_title(f"Top Fused Keyword Signals ({RECENT_YEAR_START}-{RECENT_YEAR_END})")
    ax.set_xlabel("Papers")
    ax.grid(axis="x", linestyle="--")
    for index, value in enumerate(counts.values):
        ax.text(value + max(counts.values) * 0.01, index, str(int(value)), va="center", fontsize=7)
    save_figure(fig, output_dir / "top_keywords.png")
    return {
        "figure_id": "top_keywords",
        "file": "top_keywords.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "paper_keyword_signals.csv",
        "message": "呈现显式关键词与题名摘要术语融合后的高频研究主题。",
        "status": "final",
    }


def _plot_keyword_year_heatmap(keyword_year: pd.DataFrame, output_dir: Path, *, top_n: int = 12) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keyword_year.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data = data.dropna(subset=["keyword", "year"])
    data["year"] = data["year"].astype(int)
    data = data[(data["year"] >= RECENT_YEAR_START) & (data["year"] <= RECENT_YEAR_END)]
    data = data[data["keyword"].map(_is_report_keyword)]
    top_keywords = data.groupby("keyword")["count"].sum().sort_values(ascending=False).head(top_n).index
    data = data[data["keyword"].isin(top_keywords)]
    pivot = data.pivot_table(index="keyword", columns="year", values="count", aggfunc="sum", fill_value=0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=True).index]
    pivot = pivot.reindex(columns=list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1)), fill_value=0)
    normalized = pivot.div(pivot.max(axis=1).replace(0, np.nan), axis=0).fillna(0)

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    image = ax.imshow(normalized.values, cmap=_single_color_cmap("purple_keyword_heat", PURPLE), vmin=0, vmax=1, aspect="auto")
    ax.set_title(f"Fused Keyword Evolution Heatmap ({RECENT_YEAR_START}-{RECENT_YEAR_END})")
    x_labels = [f"{int(year)} YTD" if int(year) == RECENT_YEAR_END else str(int(year)) for year in normalized.columns]
    ax.set_xticks(range(len(normalized.columns)), x_labels, rotation=45, ha="right")
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
        "message": "展示显式关键词与题名摘要术语融合后的年度热度变化。",
        "status": "final",
    }


def _plot_keyword_momentum(keyword_year: pd.DataFrame, output_dir: Path, *, top_n: int = 12) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keyword_year.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["count"] = pd.to_numeric(data["count"], errors="coerce").fillna(0)
    data = data.dropna(subset=["keyword", "year"])
    data["year"] = data["year"].astype(int)
    data = data[(data["year"] >= RECENT_YEAR_START) & (data["year"] <= RECENT_YEAR_END)]
    data = data[data["keyword"].map(_is_report_keyword)]
    baseline = data[data["year"].between(RECENT_YEAR_START, RECENT_YEAR_START + 1)]
    recent = data[data["year"].between(RECENT_YEAR_END - 2, RECENT_YEAR_END - 1)]
    baseline_counts = baseline.groupby("keyword")["count"].sum()
    recent_counts = recent.groupby("keyword")["count"].sum()
    keywords = sorted(set(baseline_counts.index).union(set(recent_counts.index)))
    rows = []
    for keyword in keywords:
        baseline_value = float(baseline_counts.get(keyword, 0))
        recent_value = float(recent_counts.get(keyword, 0))
        if recent_value <= 0:
            continue
        if recent_value < 100:
            continue
        momentum = math.log1p(recent_value) - math.log1p(baseline_value)
        support = math.log1p(recent_value + baseline_value)
        rows.append((keyword, momentum * support, recent_value, baseline_value))
    rows = sorted(rows, key=lambda item: (item[1], item[2]), reverse=True)[:top_n]
    rows = list(reversed(rows))

    labels = [_wrap_label(keyword, width=28) for keyword, *_ in rows]
    values = [score for _, score, _, _ in rows]
    fig, ax = plt.subplots(figsize=(7.4, 4.7))
    positions = np.arange(len(labels))
    colors = [SERIES_COLORS[index % len(SERIES_COLORS)] for index in range(len(labels))]
    ax.barh(positions, values, color=colors, height=0.6)
    ax.set_yticks(positions, labels)
    ax.set_xlabel("Momentum score")
    ax.set_title(f"Emerging Keyword Momentum ({RECENT_YEAR_START}-{RECENT_YEAR_END - 1}, 2026 YTD excluded)")
    ax.grid(axis="x", linestyle="--")
    max_value = max(values) if values else 1
    for position, (_, _, recent_value, baseline_value) in zip(positions, rows, strict=False):
        ax.text(
            values[position] + max_value * 0.012,
            position,
            f"{_format_count(recent_value)} vs {_format_count(baseline_value)}",
            va="center",
            fontsize=7,
        )
    save_figure(fig, output_dir / "keyword_momentum.png")
    return {
        "figure_id": "keyword_momentum",
        "file": "keyword_momentum.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "keyword_year_matrix.csv",
        "message": "比较完整近期窗口与早期窗口的融合关键词升温幅度。",
        "status": "final",
    }


def _plot_keyword_normalized_trends(keyword_trends: pd.DataFrame, output_dir: Path, *, top_n: int = 8) -> dict[str, str]:
    from matplotlib import pyplot as plt

    if keyword_trends.empty:
        raise ValueError("keyword_trends is empty")
    data = keyword_trends.copy()
    data["momentum_score"] = pd.to_numeric(data.get("momentum_score"), errors="coerce").fillna(0)
    data["doc_count"] = pd.to_numeric(data.get("doc_count"), errors="coerce").fillna(0)
    data = data[data["keyword"].map(_is_report_keyword)]
    preferred = data[data["keyword"].isin(REPRESENTATIVE_TREND_KEYWORDS)].copy()
    if not preferred.empty:
        preferred["keyword_order"] = preferred["keyword"].map({keyword: index for index, keyword in enumerate(REPRESENTATIVE_TREND_KEYWORDS)})
        data = preferred.sort_values("keyword_order").head(top_n)
    else:
        data = data.sort_values(["momentum_score", "doc_count"], ascending=False).head(top_n)
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for index, (_, row) in enumerate(data.iterrows()):
        values = [float(row.get(f"normalized_df_{year}") or 0) for year in years]
        ax.plot(
            years,
            values,
            marker="o",
            linewidth=1.5,
            markersize=3.2,
            color=SERIES_COLORS[index % len(SERIES_COLORS)],
            label=_compact_topic(row["keyword"]),
        )
    ax.set_title("Normalized Fused Keyword Document Share")
    ax.set_xlabel("Year")
    ax.set_ylabel("Documents containing term / analyzable year documents")
    ax.set_xticks(years, [f"{year} YTD" if year == RECENT_YEAR_END else str(year) for year in years])
    ax.grid(axis="y", linestyle="--")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=6.8, frameon=False)
    save_figure(fig, output_dir / "keyword_normalized_trends.png")
    return {
        "figure_id": "keyword_normalized_trends",
        "file": "keyword_normalized_trends.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "keyword_trends.csv",
        "message": "使用融合信号的年度文档占比展示关键词趋势, 避免关键词字段滞后误导。",
        "status": "final",
    }


def _plot_keyword_cooccurrence_network(
    keyword_edges: pd.DataFrame,
    keyword_metrics: pd.DataFrame,
    output_dir: Path,
    *,
    max_edges: int = 140,
    max_labels: int = 5,
) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keyword_edges.copy()
    if data.empty:
        raise ValueError("keyword_edges is empty")
    data["weight"] = pd.to_numeric(data.get("weight"), errors="coerce").fillna(0)
    data["paper_count"] = pd.to_numeric(data.get("paper_count"), errors="coerce").fillna(0)
    data = data[(data["weight"] > 0) & (data["keyword_a"].astype(str) != data["keyword_b"].astype(str))]
    filtered = data[data["keyword_a"].map(_is_report_keyword) & data["keyword_b"].map(_is_report_keyword)]
    if not filtered.empty:
        data = filtered
    data = data.sort_values(["weight", "paper_count"], ascending=False).head(max_edges)

    metric_rows = {}
    if not keyword_metrics.empty:
        metrics = keyword_metrics.copy()
        for column in ("doc_count", "weighted_degree", "pagerank"):
            if column in metrics.columns:
                metrics[column] = pd.to_numeric(metrics[column], errors="coerce").fillna(0)
        metric_rows = {str(row["keyword"]): row for _, row in metrics.iterrows() if str(row.get("keyword") or "").strip()}

    graph = nx.Graph()
    for _, row in data.iterrows():
        graph.add_edge(str(row["keyword_a"]), str(row["keyword_b"]), weight=float(row["weight"]))
    if graph.number_of_edges() == 0:
        fig, ax = plt.subplots(figsize=(7.4, 4.4))
        ax.axis("off")
        ax.text(0.5, 0.5, "No keyword co-occurrence edges available", ha="center", va="center", color=MUTED)
        save_figure(fig, output_dir / "keyword_cooccurrence_network.png")
        return {
            "figure_id": "keyword_cooccurrence_network",
            "file": "keyword_cooccurrence_network.png",
            "report_section": "关键词演化与热点趋势",
            "source_table": "keyword_cooccurrence_edges.csv;keyword_metrics.csv",
            "message": "关键词共现网络暂无可绘制边。",
            "status": "empty",
        }
    components = sorted(nx.connected_components(graph), key=len, reverse=True)
    if len(components) > 1:
        graph = graph.subgraph(components[0]).copy()

    pos = nx.spring_layout(
        graph,
        seed=43,
        weight="weight",
        k=1.85 / math.sqrt(max(graph.number_of_nodes(), 1)),
        iterations=180,
        scale=1.7,
    )
    graph_degree = dict(graph.degree(weight="weight"))
    pagerank = {
        node: float(metric_rows.get(node, {}).get("pagerank") or 0)
        for node in graph.nodes
    }
    communities = {
        node: str(metric_rows.get(node, {}).get("community_id") or "unknown")
        for node in graph.nodes
    }
    max_weight = max((float(edge.get("weight") or 0) for _, _, edge in graph.edges(data=True)), default=1.0)
    max_degree = max(graph_degree.values(), default=1.0) or 1.0

    fig, ax = plt.subplots(figsize=(8.4, 6.1))
    for source, target, edge_data in graph.edges(data=True):
        weight = float(edge_data.get("weight") or 0)
        ax.plot(
            [pos[source][0], pos[target][0]],
            [pos[source][1], pos[target][1]],
            color=CHARCOAL,
            alpha=0.14 + min(weight / max_weight, 1) * 0.34,
            linewidth=0.45 + min(weight / max_weight, 1) * 2.2,
            zorder=1,
        )

    xs = [pos[node][0] for node in graph.nodes]
    ys = [pos[node][1] for node in graph.nodes]
    sizes = [42 + 410 * math.sqrt(max(graph_degree.get(node, 0), 0) / max_degree) for node in graph.nodes]
    colors = [_community_color(communities.get(node, "unknown")) for node in graph.nodes]
    ax.scatter(xs, ys, s=sizes, c=colors, edgecolors="white", linewidths=0.55, alpha=0.92, zorder=3)

    label_candidates = sorted(
        graph.nodes,
        key=lambda node: (pagerank.get(node, 0), graph_degree.get(node, 0)),
        reverse=True,
    )
    center_x = float(np.mean(xs)) if xs else 0.0
    center_y = float(np.mean(ys)) if ys else 0.0
    placed_labels: list[tuple[float, float]] = []
    for rank, node in enumerate(label_candidates):
        if len(placed_labels) >= max_labels:
            break
        x, y = pos[node]
        dx = x - center_x
        dy = y - center_y
        distance = math.hypot(dx, dy) or 1.0
        label_radius = 0.22 + 0.05 * (rank % 3)
        label_x = x + dx / distance * label_radius
        label_y = y + dy / distance * label_radius
        if any(math.hypot(label_x - other_x, label_y - other_y) < 0.42 for other_x, other_y in placed_labels):
            continue
        placed_labels.append((label_x, label_y))
        ax.annotate(
            _wrap_label(node, width=13),
            xy=(x, y),
            xytext=(label_x, label_y),
            arrowprops={"arrowstyle": "-", "color": "0.45", "lw": 0.35, "alpha": 0.62},
            bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "0.78", "lw": 0.3, "alpha": 0.84},
            fontsize=5.2,
            ha="center",
            va="center",
            color=BLACK,
            zorder=5,
        )
    ax.set_title("Core Keyword Co-occurrence Network")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)
    ax.margins(0.22)
    ax.text(
        0.01,
        0.015,
        "Node size: weighted co-occurrence degree. Color: keyword community. Edge width: fractional paper co-occurrence.",
        transform=ax.transAxes,
        fontsize=6.4,
        color="0.25",
    )
    save_figure(fig, output_dir / "keyword_cooccurrence_network.png")
    return {
        "figure_id": "keyword_cooccurrence_network",
        "file": "keyword_cooccurrence_network.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "keyword_cooccurrence_edges.csv;keyword_metrics.csv",
        "message": "展示核心关键词共现 component, 节点颜色来自 Louvain 社区, 用于识别热点主题簇。",
        "status": "final",
    }


def _plot_keyword_lifecycle(keyword_lifecycle: pd.DataFrame, output_dir: Path, *, top_n: int = 16) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keyword_lifecycle.copy()
    if data.empty:
        raise ValueError("keyword_lifecycle is empty")
    filtered = data[data["keyword"].map(_is_report_keyword)]
    if not filtered.empty:
        data = filtered
    for column in ("doc_count", "first_year", "peak_year", "last_year", "peak_count"):
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    data["doc_count"] = data.get("doc_count", pd.Series(dtype=float)).fillna(0)
    data = data.sort_values("doc_count", ascending=False).head(top_n)
    data = data.sort_values("doc_count", ascending=True)

    fig, ax = plt.subplots(figsize=(7.8, 5.0))
    positions = np.arange(len(data))
    max_peak = float(data["doc_count"].max()) if not data.empty else 1.0
    max_peak = max_peak or 1.0
    for position, (_, row) in zip(positions, data.iterrows(), strict=False):
        first_year = int(row.get("first_year") or RECENT_YEAR_START)
        peak_year = int(row.get("peak_year") or first_year)
        last_year = int(row.get("last_year") or peak_year)
        stage = str(row.get("lifecycle_stage") or "maturity")
        color = LIFECYCLE_COLORS.get(stage, MUTED)
        ax.hlines(position, first_year, last_year, color=color, linewidth=3.0, alpha=0.48, zorder=1)
        size = 38 + 250 * math.sqrt(float(row.get("doc_count") or 0) / max_peak)
        ax.scatter([peak_year], [position], s=size, color=color, edgecolor="white", linewidth=0.55, zorder=3)
        ax.text(last_year + 0.06, position, stage, va="center", fontsize=6.4, color="0.28")
    ax.set_yticks(positions, [_wrap_label(str(keyword), width=28) for keyword in data["keyword"]])
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))
    ax.set_xticks(years, [f"{year} YTD" if year == RECENT_YEAR_END else str(year) for year in years])
    ax.set_xlim(RECENT_YEAR_START - 0.4, RECENT_YEAR_END + 0.9)
    ax.set_xlabel("First year - peak year - latest year")
    ax.set_title("Keyword Lifecycle Stage Map")
    ax.grid(axis="x", linestyle="--")
    save_figure(fig, output_dir / "keyword_lifecycle.png")
    return {
        "figure_id": "keyword_lifecycle",
        "file": "keyword_lifecycle.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "keyword_lifecycle.csv",
        "message": "将关键词划分为 emergence、growth、maturity、decline 四类生命周期阶段。",
        "status": "final",
    }


def _plot_keyword_burst_windows(keyword_bursts: pd.DataFrame, output_dir: Path, *, top_n: int = 14) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = keyword_bursts.copy()
    if data.empty:
        raise ValueError("keyword_bursts is empty")
    filtered = data[data["keyword"].map(_is_report_keyword)]
    if not filtered.empty:
        data = filtered
    for column in ("year", "growth_rate", "burst_score"):
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    data = data.sort_values(["burst_score", "growth_rate"], ascending=False).head(top_n)
    data = data.sort_values("burst_score", ascending=True)
    labels = [
        _wrap_label(f"{row['keyword']} ({int(row['year'])})", width=30)
        for _, row in data.iterrows()
    ]
    colors = [LIFECYCLE_COLORS.get(str(row.get("burst_state") or ""), MUTED) for _, row in data.iterrows()]

    fig, ax = plt.subplots(figsize=(7.7, 4.9))
    positions = np.arange(len(data))
    values = data["burst_score"].to_numpy(dtype=float)
    ax.barh(positions, values, color=colors, height=0.58)
    ax.set_yticks(positions, labels)
    ax.set_xlabel("Burst score")
    ax.set_title("Keyword Burst Windows")
    ax.grid(axis="x", linestyle="--")
    max_value = max(values) if len(values) else 1.0
    for position, (_, row) in zip(positions, data.iterrows(), strict=False):
        ax.text(
            float(row["burst_score"]) + max_value * 0.012,
            position,
            f"{row.get('burst_state') or ''} / {float(row.get('growth_rate') or 0):.2f}",
            va="center",
            fontsize=6.3,
            color="0.28",
        )
    save_figure(fig, output_dir / "keyword_burst_windows.png")
    return {
        "figure_id": "keyword_burst_windows",
        "file": "keyword_burst_windows.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "keyword_burst_windows.csv",
        "message": "标出关键词在年度窗口中的突发增长、萌发或回落变化。",
        "status": "final",
    }


def _plot_topic_year_share(topic_year: pd.DataFrame, output_dir: Path, *, model: str = "nmf") -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = topic_year.copy()
    data = data[data["model"].astype(str) == model]
    if data.empty:
        data = topic_year.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["paper_count"] = pd.to_numeric(data["paper_count"], errors="coerce").fillna(0)
    data = data.dropna(subset=["year"])
    data["year"] = data["year"].astype(int)
    data = data[(data["year"] >= RECENT_YEAR_START) & (data["year"] <= RECENT_YEAR_END)]
    pivot = data.pivot_table(index="year", columns="topic_id", values="paper_count", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(index=list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1)), fill_value=0)
    shares = pivot.div(pivot.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    bottom = np.zeros(len(shares.index))
    for index, topic_id in enumerate(shares.columns):
        values = shares[topic_id].to_numpy()
        ax.bar(
            [f"{int(year)} YTD" if int(year) == RECENT_YEAR_END else str(int(year)) for year in shares.index],
            values,
            bottom=bottom,
            color=SERIES_COLORS[index % len(SERIES_COLORS)],
            edgecolor="white",
            linewidth=0.35,
            label=f"T{topic_id}",
        )
        bottom = bottom + values
    ax.set_title(f"Topic Year Share ({model.upper()} baseline)")
    ax.set_ylabel("Share within year")
    ax.set_ylim(0, 1.02)
    ax.set_yticks(np.linspace(0, 1, 6), [f"{int(value * 100)}%" for value in np.linspace(0, 1, 6)])
    ax.legend(ncol=4, fontsize=6.8, loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
    save_figure(fig, output_dir / "topic_year_share.png")
    return {
        "figure_id": "topic_year_share",
        "file": "topic_year_share.png",
        "report_section": "关键词演化与热点趋势",
        "source_table": "topic_year_share.csv",
        "message": "展示主题模型基线中各主题在年度语料中的占比变化。",
        "status": "final",
    }


def _numeric_series(data: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in data:
        return pd.Series([default] * len(data), index=data.index)
    return pd.to_numeric(data[column], errors="coerce").fillna(default)


def _prepare_author_plot_edges(author_edges: pd.DataFrame) -> pd.DataFrame:
    if author_edges.attrs.get("author_plot_edges_prepared"):
        return author_edges

    data = author_edges.copy()
    if data.empty:
        return data
    if "author_a_key" not in data:
        data["author_a_key"] = data["author_a"]
    if "author_b_key" not in data:
        data["author_b_key"] = data["author_b"]
    if "author_a" not in data:
        data["author_a"] = data["author_a_key"]
    if "author_b" not in data:
        data["author_b"] = data["author_b_key"]

    data["author_a_key"] = data["author_a_key"].astype(str)
    data["author_b_key"] = data["author_b_key"].astype(str)
    data["author_a"] = data["author_a"].astype(str)
    data["author_b"] = data["author_b"].astype(str)
    if "long_author_papers" in data:
        core_data = data[_numeric_series(data, "long_author_papers", 0.0) == 0].copy()
        if not core_data.empty:
            data = core_data
    data["plot_weight"] = _numeric_series(data, "weight_fraction_pair", 0.0)
    if not float(data["plot_weight"].max() or 0):
        data["plot_weight"] = _numeric_series(data, "weight", 0.0)
    sort_columns = ["plot_weight"]
    if "paper_count" in data:
        sort_columns.append("paper_count")
    data = data.sort_values(sort_columns, ascending=False)
    data.attrs["author_plot_edges_prepared"] = True
    return data


def _author_metric_lookup(author_metrics: pd.DataFrame) -> dict[str, Any]:
    if author_metrics.empty:
        return {}
    metrics = author_metrics.copy()
    if "author_key" not in metrics:
        metrics["author_key"] = metrics["author"]
    return {str(row["author_key"]): row for _, row in metrics.iterrows()}


def _metric_float(metric: Any, column: str, default: float = 0.0) -> float:
    if metric is None:
        return default
    value = pd.to_numeric(metric.get(column), errors="coerce")
    if pd.isna(value):
        return default
    return float(value)


def _metric_text(metric: Any, column: str, default: str = "") -> str:
    if metric is None:
        return default
    value = metric.get(column)
    if pd.isna(value):
        return default
    text = str(value).strip()
    return text or default


def _select_core_component_edges(data: pd.DataFrame, *, max_pool_edges: int = 25_000) -> pd.DataFrame:
    pool = data.head(max_pool_edges).copy()
    if pool.empty:
        return pool
    graph = nx.Graph()
    for _, row in pool.iterrows():
        graph.add_edge(str(row["author_a_key"]), str(row["author_b_key"]))
    components = sorted(nx.connected_components(graph), key=len, reverse=True)
    if not components:
        return pool
    if len(components[0]) >= 30:
        selected_nodes = set(components[0])
    else:
        selected_nodes: set[str] = set()
        for component in components:
            if len(component) < 2:
                continue
            selected_nodes.update(component)
            if len(selected_nodes) >= 220:
                break
    selected = pool[
        pool["author_a_key"].astype(str).isin(selected_nodes)
        & pool["author_b_key"].astype(str).isin(selected_nodes)
    ].copy()
    return selected if not selected.empty else pool


def _plot_author_core_network(
    author_edges: pd.DataFrame,
    author_metrics: pd.DataFrame,
    output_dir: Path,
    *,
    max_edges: int = 220,
    max_labels: int = 8,
) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = _prepare_author_plot_edges(author_edges)
    if data.empty:
        fig, ax = plt.subplots(figsize=(7.4, 4.4))
        ax.axis("off")
        ax.text(0.5, 0.5, "No author collaboration edges available", ha="center", va="center", color=MUTED)
        save_figure(fig, output_dir / "author_collaboration_network.png")
        return {
            "figure_id": "author_core_network",
            "file": "author_collaboration_network.png",
            "report_section": "作者合作网络分析",
            "source_table": "author_collaboration_edges.csv;author_metrics.csv",
            "message": "作者合作核心网络暂无可绘制边。",
            "status": "empty",
        }

    component_edges = _select_core_component_edges(data)
    data = component_edges.head(max_edges)

    metric_rows = _author_metric_lookup(author_metrics)

    graph = nx.Graph()
    labels: dict[str, str] = {}
    communities: dict[str, str] = {}
    pagerank: dict[str, float] = {}
    betweenness: dict[str, float] = {}
    degree: dict[str, float] = {}
    for _, row in data.iterrows():
        source = str(row["author_a_key"])
        target = str(row["author_b_key"])
        labels[source] = str(row.get("author_a") or source)
        labels[target] = str(row.get("author_b") or target)
        graph.add_edge(source, target, weight=float(row["plot_weight"]))
    for node in graph.nodes:
        metric = metric_rows.get(node)
        if metric is not None:
            labels[node] = _metric_text(metric, "author", labels.get(node) or node)
            communities[node] = _metric_text(metric, "community_id", "unknown")
            pagerank[node] = _metric_float(metric, "pagerank")
            betweenness[node] = _metric_float(metric, "betweenness")
            degree[node] = _metric_float(metric, "degree")
        else:
            communities[node] = "unknown"
            degree[node] = float(graph.degree(node, weight="weight"))

    fig, ax = plt.subplots(figsize=(8.6, 6.5))
    if graph.number_of_edges():
        pos = nx.spring_layout(
            graph,
            seed=42,
            weight="weight",
            k=1.05 / math.sqrt(max(graph.number_of_nodes(), 1)),
            iterations=160,
            scale=1.35,
        )
    else:
        pos = nx.circular_layout(graph)

    max_weight = max((float(data.get("weight") or 0) for _, _, data in graph.edges(data=True)), default=1.0)
    for source, target, edge_data in graph.edges(data=True):
        weight = float(edge_data.get("weight") or 0)
        ax.plot(
            [pos[source][0], pos[target][0]],
            [pos[source][1], pos[target][1]],
            color=CHARCOAL,
            alpha=0.16 + min(weight / max_weight, 1) * 0.3,
            linewidth=0.45 + min(weight / max_weight, 1) * 2.1,
            zorder=1,
        )

    max_degree = max(degree.values(), default=1.0) or 1.0
    xs = [pos[node][0] for node in graph.nodes]
    ys = [pos[node][1] for node in graph.nodes]
    sizes = [35 + 460 * math.sqrt(max(degree.get(node, 0), 0) / max_degree) for node in graph.nodes]
    colors = [_community_color(communities.get(node, "unknown")) for node in graph.nodes]
    ax.scatter(xs, ys, s=sizes, c=colors, edgecolors="white", linewidths=0.55, alpha=0.92, zorder=3)

    label_nodes = sorted(
        graph.nodes,
        key=lambda node: (betweenness.get(node, 0), pagerank.get(node, 0), degree.get(node, 0)),
        reverse=True,
    )[:max_labels]
    for node in label_nodes:
        x, y = pos[node]
        center_x = float(np.mean(xs)) if xs else 0.0
        center_y = float(np.mean(ys)) if ys else 0.0
        dx = x - center_x
        dy = y - center_y
        distance = math.hypot(dx, dy) or 1.0
        label_x = x + dx / distance * 0.14
        label_y = y + dy / distance * 0.14
        ax.annotate(
            _wrap_label(labels.get(node, node), width=16),
            xy=(x, y),
            xytext=(label_x, label_y),
            arrowprops={"arrowstyle": "-", "color": "0.45", "lw": 0.35, "alpha": 0.65},
            bbox={"boxstyle": "round,pad=0.16", "fc": "white", "ec": "0.75", "lw": 0.35, "alpha": 0.84},
            fontsize=5.4,
            ha="center",
            va="center",
            color=BLACK,
            zorder=5,
        )
    ax.set_title(f"Core Author Collaboration Network ({len(data):,} displayed edges)")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)
    ax.margins(0.14)
    ax.text(
        0.01,
        0.015,
        "Labels show the top bridge/core authors only. Node size: weighted degree/PageRank proxy. Edge width: fractional coauthor weight.",
        transform=ax.transAxes,
        fontsize=6.5,
        color="0.25",
    )
    save_figure(fig, output_dir / "author_collaboration_network.png")
    return {
        "figure_id": "author_core_network",
        "file": "author_collaboration_network.png",
        "report_section": "作者合作网络分析",
        "source_table": "author_collaboration_edges.csv;author_metrics.csv",
        "message": "展示核心作者实体合作网络, 节点颜色来自 Louvain 社区, 边宽来自分数化合作权重。",
        "status": "final",
    }


def _component_plot_slices(
    data: pd.DataFrame,
    *,
    max_pool_edges: int = 60_000,
    max_components: int = 16,
    max_nodes_per_component: int = 10,
    max_edges_per_component: int = 16,
) -> list[dict[str, Any]]:
    pool = data.head(max_pool_edges).copy()
    if pool.empty:
        return []

    graph = nx.Graph()
    for _, row in pool.iterrows():
        source = str(row["author_a_key"])
        target = str(row["author_b_key"])
        if not source or not target or source == target:
            continue
        graph.add_edge(source, target, weight=float(row["plot_weight"]))
    if graph.number_of_edges() == 0:
        return []

    slices: list[dict[str, Any]] = []
    for component in nx.connected_components(graph):
        if len(component) < 2:
            continue
        component_nodes = set(component)
        component_edges = pool[
            pool["author_a_key"].isin(component_nodes)
            & pool["author_b_key"].isin(component_nodes)
        ].copy()
        if component_edges.empty:
            continue
        node_scores: Counter[str] = Counter()
        for _, edge in component_edges.iterrows():
            weight = float(edge["plot_weight"])
            node_scores[str(edge["author_a_key"])] += weight
            node_scores[str(edge["author_b_key"])] += weight
        component_edges = component_edges.sort_values("plot_weight", ascending=False)
        anchor_node = max(node_scores, key=lambda node: node_scores[node])
        selected_nodes = {anchor_node}
        while len(selected_nodes) < max_nodes_per_component:
            next_edge = None
            for _, edge in component_edges.iterrows():
                source = str(edge["author_a_key"])
                target = str(edge["author_b_key"])
                if (source in selected_nodes) ^ (target in selected_nodes):
                    next_edge = (source, target)
                    break
            if next_edge is None:
                break
            selected_nodes.update(next_edge)
        plot_edges = component_edges[
            component_edges["author_a_key"].isin(selected_nodes)
            & component_edges["author_b_key"].isin(selected_nodes)
        ].head(max_edges_per_component)
        if plot_edges.empty:
            plot_edges = component_edges.head(1)
        slices.append(
            {
                "nodes_total": len(component_nodes),
                "edges_total": len(component_edges),
                "total_weight": float(component_edges["plot_weight"].sum()),
                "plot_edges": plot_edges,
                "node_scores": node_scores,
            }
        )
    return sorted(slices, key=lambda item: (item["total_weight"], item["nodes_total"]), reverse=True)[:max_components]


def _plot_author_component_overview(
    author_edges: pd.DataFrame,
    author_metrics: pd.DataFrame,
    output_dir: Path,
    *,
    max_components: int = 16,
) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = _prepare_author_plot_edges(author_edges)
    slices = _component_plot_slices(data, max_components=max_components)
    output_file = output_dir / "author_component_overview.png"
    if not slices:
        fig, ax = plt.subplots(figsize=(7.4, 4.4))
        ax.axis("off")
        ax.text(0.5, 0.5, "No author collaboration components available", ha="center", va="center", color=MUTED)
        save_figure(fig, output_file)
        return {
            "figure_id": "author_component_overview",
            "file": output_file.name,
            "report_section": "作者合作网络分析",
            "source_table": "author_collaboration_edges.csv;author_metrics.csv",
            "message": "author component overview 暂无可绘制组件。",
            "status": "empty",
        }

    metric_rows = _author_metric_lookup(author_metrics)
    columns = 4
    rows = math.ceil(len(slices) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(8.6, 1.86 * rows + 0.55), squeeze=False)
    fig.suptitle("Author Collaboration Component Overview", fontsize=10)
    for index, item in enumerate(slices):
        ax = axes[index // columns][index % columns]
        plot_edges = item["plot_edges"]
        component_graph = nx.Graph()
        labels: dict[str, str] = {}
        communities: dict[str, str] = {}
        for _, edge in plot_edges.iterrows():
            source = str(edge["author_a_key"])
            target = str(edge["author_b_key"])
            component_graph.add_edge(source, target, weight=float(edge["plot_weight"]))
            labels[source] = str(edge.get("author_a") or source)
            labels[target] = str(edge.get("author_b") or target)
        for node in component_graph.nodes:
            metric = metric_rows.get(node)
            labels[node] = _metric_text(metric, "author", labels.get(node, node))
            communities[node] = _metric_text(metric, "community_id", "unknown")

        if component_graph.number_of_nodes() <= 2:
            pos = nx.circular_layout(component_graph)
        else:
            pos = nx.spring_layout(
                component_graph,
                seed=42 + index,
                weight="weight",
                k=0.95 / math.sqrt(max(component_graph.number_of_nodes(), 1)),
                iterations=90,
            )
        max_weight = max((float(edge.get("weight") or 0) for _, _, edge in component_graph.edges(data=True)), default=1.0)
        for source, target, edge_data in component_graph.edges(data=True):
            weight = float(edge_data.get("weight") or 0)
            ax.plot(
                [pos[source][0], pos[target][0]],
                [pos[source][1], pos[target][1]],
                color=CHARCOAL,
                alpha=0.28 + min(weight / max_weight, 1) * 0.28,
                linewidth=0.5 + min(weight / max_weight, 1) * 1.7,
                zorder=1,
            )

        node_scores = item["node_scores"]
        max_score = max((node_scores.get(str(node), 0) for node in component_graph.nodes), default=1.0) or 1.0
        xs = [pos[node][0] for node in component_graph.nodes]
        ys = [pos[node][1] for node in component_graph.nodes]
        sizes = [42 + 170 * math.sqrt(max(node_scores.get(str(node), 0), 0) / max_score) for node in component_graph.nodes]
        colors = [_community_color(communities.get(node, "unknown")) for node in component_graph.nodes]
        ax.scatter(xs, ys, s=sizes, c=colors, edgecolors="white", linewidths=0.45, alpha=0.92, zorder=3)

        top_node = max(component_graph.nodes, key=lambda node: node_scores.get(str(node), 0))
        ax.set_title(f"C{index + 1}: {item['nodes_total']} nodes / {item['edges_total']} edges", fontsize=6.8)
        x, y = pos[top_node]
        center_x = float(np.mean(xs)) if xs else 0.0
        center_y = float(np.mean(ys)) if ys else 0.0
        dx = x - center_x
        dy = y - center_y
        distance = math.hypot(dx, dy) or 1.0
        ax.annotate(
            _wrap_label(labels.get(top_node, top_node), width=16),
            xy=(x, y),
            xytext=(x + dx / distance * 0.18, y + dy / distance * 0.18),
            arrowprops={"arrowstyle": "-", "color": "0.48", "lw": 0.3, "alpha": 0.62},
            fontsize=5.2,
            ha="center",
            va="center",
            color=BLACK,
            bbox={"boxstyle": "round,pad=0.13", "fc": "white", "ec": "0.82", "lw": 0.25, "alpha": 0.84},
            zorder=5,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_frame_on(False)
        ax.margins(0.18)

    for index in range(len(slices), rows * columns):
        axes[index // columns][index % columns].axis("off")
    fig.text(
        0.01,
        0.01,
        "Each panel is a high-weight connected component; only its strongest local edges and one anchor author are labeled.",
        fontsize=6.4,
        color="0.25",
    )
    save_figure(fig, output_file)
    return {
        "figure_id": "author_component_overview",
        "file": output_file.name,
        "report_section": "作者合作网络分析",
        "source_table": "author_collaboration_edges.csv;author_metrics.csv",
        "message": f"author component overview 展示 {len(slices)} 个高权重合作组件, 用于补充核心单组件网络。",
        "status": "final",
    }


def _plot_author_network_scale(
    papers: list[dict[str, Any]],
    output_dir: Path,
    diagnostics: pd.DataFrame | None = None,
    *,
    graph_edges: int = 25_000,
) -> dict[str, str]:
    from matplotlib import pyplot as plt

    diagnostic_map = {}
    if diagnostics is not None and not diagnostics.empty:
        diagnostic_map = {str(row["metric"]): row["value"] for _, row in diagnostics.iterrows()}
    scope = _recent_author_scope(papers) if not diagnostic_map else {}
    recent_papers = len(_recent_papers(papers))
    total_records = len(papers)
    values = [
        recent_papers,
        int(diagnostic_map.get("papers_with_authors") or scope.get("valid_papers") or 0),
        int(diagnostic_map.get("unique_author_keys") or len(scope.get("authors", []))),
        int(diagnostic_map.get("coauthor_edges") or len(scope.get("edge_counts", []))),
        int(diagnostic_map.get("core_graph_edges") or min(graph_edges, len(scope.get("edge_counts", [])))),
    ]
    labels = [
        "Recent papers",
        "Coauthor-valid papers",
        "Informative authors",
        "Weighted coauthor edges",
        "Core graph edges",
    ]
    positions = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.barh(positions, values, color=[PURPLE_LIGHT, BLUE_LIGHT, BROWN_LIGHT, BLUE, PURPLE], edgecolor="white", linewidth=0.8)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("Count (log scale)")
    ax.set_title(
        f"Author Network Scale Funnel ({RECENT_YEAR_START}-{RECENT_YEAR_END}: "
        f"{_format_count(recent_papers)} / {_format_count(total_records)} records)"
    )
    ax.grid(axis="x", linestyle="--")
    for position, value in zip(positions, values, strict=False):
        ax.text(value * 1.05, position, _format_count(value), va="center", fontsize=7)
    save_figure(fig, output_dir / "author_network_scale_funnel.png")
    return {
        "figure_id": "author_network_scale",
        "file": "author_network_scale_funnel.png",
        "report_section": "作者合作网络分析",
        "source_table": "papers_clean.json",
        "message": "展示从近五年论文到核心作者合作图的规模压缩过程。",
        "status": "final",
    }


def _plot_top_author_collaborations(author_edges: pd.DataFrame, output_dir: Path, *, top_n: int = 20) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = _prepare_author_plot_edges(author_edges)
    if data.empty:
        data = pd.DataFrame(columns=["author_a", "author_b", "plot_weight"])
    data = data.head(top_n)
    candidate_edges = len(author_edges)
    labels = [_wrap_label(f"{row['author_a']} / {row['author_b']}", width=32) for _, row in data.iterrows()]
    values = [float(value) for value in data["plot_weight"]]

    fig, ax = plt.subplots(figsize=(7.6, 6.2))
    positions = np.arange(len(labels))
    colors = [SERIES_COLORS[index % len(SERIES_COLORS)] for index in range(len(labels))]
    ax.barh(positions, values, color=colors, height=0.58)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Fractional Collaboration Weight")
    ax.set_title(
        f"Top Repeated Author Collaborations "
        f"(top {len(data)}/{_format_count(candidate_edges)} weighted edges)"
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
        "source_table": "author_collaboration_edges.csv",
        "message": "列出高权重作者实体合作关系, 使用分析表中的分数化边权。",
        "status": "final",
    }


def _plot_text_coverage(quality: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    from matplotlib import pyplot as plt

    data = quality.sort_values("source")
    abstract_rate = data["abstract_count"].astype(float) / data["records"].replace(0, np.nan).astype(float)
    full_text_rate = data["full_text_count"].astype(float) / data["records"].replace(0, np.nan).astype(float)
    full_text_counts = data["full_text_count"].astype(int)
    total_full_text = int(full_text_counts.sum())
    total_records = int(data["records"].astype(int).sum())
    x = np.arange(len(data))
    width = 0.34

    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    ax.bar(x - width / 2, abstract_rate.fillna(0), width, label="Abstract", color=PURPLE)
    ax.bar(x + width / 2, full_text_rate.fillna(0), width, label="Full text", color=BROWN, edgecolor="white", linewidth=0.6)
    ax.set_title(f"Abstract and Full-text Coverage (full text n={_format_count(total_full_text)})")
    ax.set_ylabel("Coverage")
    ax.set_ylim(0, 1.08)
    ax.set_xticks(x, data["source"], rotation=25, ha="right")
    ax.set_yticks(np.linspace(0, 1, 6), [f"{int(value * 100)}%" for value in np.linspace(0, 1, 6)])
    ax.grid(axis="y", linestyle="--")
    ax.legend(loc="upper right")
    for index, (rate, count) in enumerate(zip(full_text_rate.fillna(0), full_text_counts, strict=False)):
        if count:
            ax.text(
                index + width / 2,
                min(float(rate) + 0.035, 1.02),
                _format_count(count),
                ha="center",
                va="bottom",
                fontsize=7,
            )
    save_figure(fig, output_dir / "abstract_fulltext_coverage.png")
    return {
        "figure_id": "text_coverage",
        "file": "abstract_fulltext_coverage.png",
        "report_section": "数据质量与可信度审计",
        "source_table": "source_quality_report.csv",
        "message": (
            f"Full-text records: {_format_count(total_full_text)} / {_format_count(total_records)}. "
            "区分摘要级分析和全文级 RAG 的证据边界。"
        ),
        "status": "final",
    }


def build_report_figures(
    *,
    analysis_dir: str | Path = "data/analysis",
    output_dir: str | Path = "output/assets/sciscope_data_report",
) -> dict[str, Any]:
    """Build chart assets used by report templates.

    Inputs are optional per table; missing upstream tables are skipped so a partial
    rebuild can still produce a consumable manifest for downstream report jobs.
    """
    configure_plot_style()
    analysis_path = Path(analysis_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    papers = _load_papers(analysis_path / "papers_clean.json")
    quality = _read_csv(analysis_path / "source_quality_report.csv")
    keywords = _read_csv(analysis_path / "paper_keyword_signals.csv")
    if keywords.empty:
        keywords = _read_csv(analysis_path / "paper_keywords.csv")
    keyword_year = _read_csv(analysis_path / "keyword_year_matrix.csv")
    keyword_trends = _read_csv(analysis_path / "keyword_trends.csv")
    keyword_edges = _read_csv(analysis_path / "keyword_cooccurrence_edges.csv")
    keyword_metrics = _read_csv(analysis_path / "keyword_metrics.csv")
    keyword_lifecycle = _read_csv(analysis_path / "keyword_lifecycle.csv")
    keyword_bursts = _read_csv(analysis_path / "keyword_burst_windows.csv")
    topic_year = _read_csv(analysis_path / "topic_year_share.csv")
    author_edges = _read_csv(analysis_path / "author_collaboration_edges.csv")
    author_metrics = _read_csv(analysis_path / "author_metrics.csv")
    author_diagnostics = _read_csv(analysis_path / "author_network_diagnostics.csv")

    # Keep report-boundary contract explicit: only emit figure rows for assets that
    # were actually generated in this run, then materialize figure_manifest.csv for
    # downstream reuse.
    manifest: list[dict[str, str]] = []
    if not quality.empty:
        manifest.append(_plot_source_records(quality, output_path))
        manifest.append(_plot_quality_matrix(quality, output_path))
        manifest.append(_plot_text_coverage(quality, output_path))
    if papers:
        manifest.append(_plot_year_distribution(papers, output_path))
        manifest.append(_plot_source_year_heatmap(papers, output_path))
        manifest.append(_plot_field_distribution(papers, output_path))
        manifest.append(_plot_field_year_heatmap(papers, output_path))
    if not keywords.empty:
        manifest.append(_plot_top_keywords(keywords, output_path))
    if not keyword_year.empty:
        manifest.append(_plot_keyword_year_heatmap(keyword_year, output_path))
        manifest.append(_plot_keyword_momentum(keyword_year, output_path))
    if not keyword_trends.empty:
        manifest.append(_plot_keyword_normalized_trends(keyword_trends, output_path))
    if not keyword_edges.empty:
        manifest.append(_plot_keyword_cooccurrence_network(keyword_edges, keyword_metrics, output_path))
    if not keyword_lifecycle.empty:
        manifest.append(_plot_keyword_lifecycle(keyword_lifecycle, output_path))
    if not keyword_bursts.empty:
        manifest.append(_plot_keyword_burst_windows(keyword_bursts, output_path))
    if not topic_year.empty:
        manifest.append(_plot_topic_year_share(topic_year, output_path))
    if papers:
        manifest.append(_plot_author_network_scale(papers, output_path, author_diagnostics))
    if not author_edges.empty:
        author_plot_edges = _prepare_author_plot_edges(author_edges)
        manifest.append(_plot_author_core_network(author_plot_edges, author_metrics, output_path))
        manifest.append(_plot_author_component_overview(author_plot_edges, author_metrics, output_path))
        manifest.append(_plot_top_author_collaborations(author_plot_edges, output_path))

    _write_manifest(output_path / "figure_manifest.csv", manifest)
    return {
        "figures": len(manifest),
        "analysis_dir": str(analysis_path),
        "output_dir": str(output_path),
        "manifest": str(output_path / "figure_manifest.csv"),
    }
