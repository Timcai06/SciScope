from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import networkx as nx

from src.harvest.normalize import paper_wrapper_to_paper


DEFAULT_SOURCES = ("openalex", "arxiv", "pubmed", "pmc", "crossref", "doaj")
RECENT_YEAR_START = 2022
RECENT_YEAR_END = 2026
MAX_AUTHORS_FOR_CORE_NETWORK = 12
TOPIC_SAMPLE_LIMIT = 50_000

KEYWORD_ALIASES = {
    "retrieval-augmented generation": "retrieval augmented generation",
    "retrieval augmented generation": "retrieval augmented generation",
    "rag": "retrieval augmented generation",
    "large language models": "large language model",
    "large-language models": "large language model",
    "llms": "large language model",
    "g n n": "graph neural network",
    "graph neural networks": "graph neural network",
    "knowledge graphs": "knowledge graph",
    "machine-learning": "machine learning",
    "deep-learning": "deep learning",
}

GENERIC_KEYWORDS = {
    "article",
    "chemistry",
    "computer science",
    "health sciences",
    "humans",
    "life sciences",
    "materials science",
    "medicine",
    "method",
    "methods",
    "model",
    "models",
    "science",
    "scientific reports",
    "study",
}


def _iter_wrappers(
    raw_dir: Path,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    filename_template: str | None = None,
):
    for source in sources:
        source_dir = raw_dir / source
        if not source_dir.exists():
            continue
        paths = [source_dir / filename_template.format(source=source)] if filename_template else sorted(source_dir.glob("*.jsonl"))
        for path in paths:
            if not path.exists():
                continue
            if path.name.endswith(".tmp") or ".tmp" in path.suffixes:
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        yield None


def _dedupe_key(paper: dict[str, Any], wrapper: dict[str, Any]) -> str:
    paper_id = str(paper.get("paper_id") or "").strip()
    source = str(wrapper.get("source") or "").strip()
    if paper_id:
        return f"{source}:{paper_id}"
    return f"{paper.get('title') or ''}::{paper.get('year') or ''}".lower()


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _paper_with_source(wrapper: dict[str, Any]) -> dict[str, Any]:
    paper = paper_wrapper_to_paper(wrapper)
    year_status = str(wrapper.get("_sciscope_year_status") or "normal")
    if year_status == "future_year_suspect":
        paper = {
            **paper,
            "year": "",
            "original_year": wrapper.get("_sciscope_original_year"),
            "year_status": year_status,
        }
    return {
        **paper,
        "source": str(wrapper.get("source") or ""),
        "source_id": str(wrapper.get("source_id") or ""),
        "query": str(wrapper.get("query") or ""),
        "field_seed": str(wrapper.get("field_seed") or ""),
        "crawled_at": str(wrapper.get("crawled_at") or ""),
        "text_for_analysis": _text_for_analysis(paper),
    }


def _year_value(value: Any) -> int | None:
    if str(value or "").isdigit():
        return int(value)
    return None


def _is_recent_year(value: Any) -> bool:
    year = _year_value(value)
    return year is not None and RECENT_YEAR_START <= year <= RECENT_YEAR_END


def _normalize_keyword(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    text = text.replace("_", " ")
    text = re.sub(r"[-/]+", " ", text)
    text = re.sub(r"[^a-z0-9 +#]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 4 and text.endswith("ies"):
        text = f"{text[:-3]}y"
    elif len(text) > 4 and text.endswith("s") and not text.endswith("ss"):
        text = text[:-1]
    return KEYWORD_ALIASES.get(text, text)


def _is_keyword_signal(value: str) -> bool:
    keyword = _normalize_keyword(value)
    if len(keyword) < 3 or keyword in GENERIC_KEYWORDS:
        return False
    if re.fullmatch(r"[a-z]{1,5}\.[a-z0-9.-]{1,12}", keyword):
        return False
    if keyword.isdigit():
        return False
    return True


def _text_for_analysis(paper: dict[str, Any]) -> str:
    title = str(paper.get("title") or "").strip()
    abstract = str(paper.get("abstract") or "").strip()
    return re.sub(r"\s+", " ", f"{title} {title} {abstract}").strip()


def _raw_paths(raw_path: Path, sources: tuple[str, ...], filename_template: str | None) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []
    for source in sources:
        source_dir = raw_path / source
        if not source_dir.exists():
            continue
        candidates = [source_dir / filename_template.format(source=source)] if filename_template else sorted(source_dir.glob("*.jsonl"))
        for path in candidates:
            if path.exists() and not path.name.endswith(".tmp") and ".tmp" not in path.suffixes:
                paths.append((source, path))
    return paths


def _build_collection_manifest(raw_path: Path, sources: tuple[str, ...], filename_template: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    year_pattern = re.compile(r"(19|20)\d{2}")
    for source, path in _raw_paths(raw_path, sources, filename_template):
        records = 0
        invalid_json = 0
        years: Counter[str] = Counter()
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                records += 1
                try:
                    wrapper = json.loads(line)
                except json.JSONDecodeError:
                    invalid_json += 1
                    continue
                status = str(wrapper.get("_sciscope_year_status") or "")
                year = wrapper.get("_sciscope_original_year") if status == "future_year_suspect" else None
                if year is None:
                    year = wrapper.get("_sciscope_canonical_year")
                if year is None:
                    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
                    year = raw.get("year") or raw.get("publication_year") or raw.get("publishedDate") or raw.get("published")
                match = year_pattern.search(str(year or ""))
                years[match.group(0) if match else "unknown_year"] += 1
        file_year = path.stem if path.stem.isdigit() else ""
        abnormal_years = sorted(year for year in years if year.isdigit() and int(year) > RECENT_YEAR_END)
        rows.append(
            {
                "source": source,
                "year_partition": file_year or path.stem,
                "file": str(path),
                "records": records,
                "file_size_bytes": path.stat().st_size,
                "empty_file": records == 0,
                "invalid_json_lines": invalid_json,
                "observed_years": ";".join(f"{year}:{count}" for year, count in sorted(years.items())),
                "abnormal_years": ";".join(abnormal_years),
            }
        )
    summary = {
        "collection_files": len(rows),
        "collection_records": sum(int(row["records"]) for row in rows),
        "empty_files": sum(1 for row in rows if row["empty_file"]),
        "invalid_json_lines": sum(int(row["invalid_json_lines"]) for row in rows),
        "abnormal_year_files": sum(1 for row in rows if row["abnormal_years"]),
    }
    return rows, summary


def _doc_key(paper: dict[str, Any]) -> str:
    return str(paper.get("paper_id") or paper.get("title") or id(paper))


def _build_keyword_assets(papers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    paper_keywords: list[dict[str, Any]] = []
    alias_rows: dict[str, str] = {}
    keyword_year_docs: dict[tuple[str, int], set[str]] = defaultdict(set)
    keyword_representatives: dict[str, dict[str, Any]] = {}
    docs_by_year = Counter(int(paper["year"]) for paper in papers if _is_recent_year(paper.get("year")))

    for paper in papers:
        year = _year_value(paper.get("year"))
        paper_id = _doc_key(paper)
        seen_keywords: set[str] = set()
        for raw_keyword in paper.get("keywords") or []:
            keyword = _normalize_keyword(raw_keyword)
            if not keyword or not _is_keyword_signal(keyword) or keyword in seen_keywords:
                continue
            seen_keywords.add(keyword)
            alias_rows[str(raw_keyword).strip().lower()] = keyword
            row = {"paper_id": str(paper.get("paper_id") or ""), "source": str(paper.get("source") or ""), "year": paper.get("year") or "", "keyword": keyword}
            paper_keywords.append(row)
            if year is not None:
                keyword_year_docs[(keyword, year)].add(paper_id)
            if keyword not in keyword_representatives or _is_recent_year(paper.get("year")):
                keyword_representatives[keyword] = paper

    keyword_year_rows: list[dict[str, Any]] = []
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))
    for (keyword, year), docs in sorted(keyword_year_docs.items(), key=lambda item: (item[0][0], item[0][1])):
        total_docs = docs_by_year.get(year, 0)
        count = len(docs)
        keyword_year_rows.append(
            {
                "keyword": keyword,
                "year": year,
                "count": count,
                "total_docs_in_year": total_docs,
                "normalized_df": round(count / total_docs, 6) if total_docs else 0,
            }
        )

    grouped_counts: dict[str, dict[int, int]] = defaultdict(dict)
    grouped_norms: dict[str, dict[int, float]] = defaultdict(dict)
    for row in keyword_year_rows:
        keyword = str(row["keyword"])
        year = int(row["year"])
        grouped_counts[keyword][year] = int(row["count"])
        grouped_norms[keyword][year] = float(row["normalized_df"])

    trend_rows: list[dict[str, Any]] = []
    for keyword, year_counts in grouped_counts.items():
        recent_values = [grouped_norms[keyword].get(year, 0.0) for year in years]
        baseline = sum(recent_values[:2]) / 2
        current = sum(recent_values[-2:]) / 2
        doc_count = sum(year_counts.get(year, 0) for year in years)
        if doc_count <= 0:
            continue
        growth_rate = (current - baseline) / baseline if baseline else (current if current else 0)
        burst_score = max(recent_values) / (sum(recent_values) / len(recent_values)) if sum(recent_values) else 0
        momentum = math.log1p(doc_count) * (growth_rate + current)
        representative = keyword_representatives.get(keyword, {})
        row = {
            "keyword": keyword,
            "doc_count": doc_count,
            "normalized_df": round(sum(recent_values) / len(recent_values), 6),
            "growth_rate": round(growth_rate, 6),
            "momentum_score": round(momentum, 6),
            "burst_score": round(burst_score, 6),
            "representative_paper_id": representative.get("paper_id") or "",
            "representative_title": representative.get("title") or "",
            "representative_year": representative.get("year") or "",
        }
        for year in years:
            row[f"doc_count_{year}"] = year_counts.get(year, 0)
            row[f"normalized_df_{year}"] = round(grouped_norms[keyword].get(year, 0.0), 6)
        trend_rows.append(row)
    trend_rows.sort(key=lambda row: (float(row["momentum_score"]), int(row["doc_count"])), reverse=True)
    alias_output = [{"raw_keyword": raw, "canonical_keyword": canonical} for raw, canonical in sorted(alias_rows.items()) if raw != canonical]
    return paper_keywords, keyword_year_rows, trend_rows, alias_output


def _build_author_assets(papers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    paper_authors: list[dict[str, Any]] = []
    edge_stats: dict[tuple[str, str], dict[str, Any]] = {}
    author_years: dict[str, Counter[int]] = defaultdict(Counter)
    author_fields: dict[str, Counter[str]] = defaultdict(Counter)
    author_collaborators: dict[str, set[str]] = defaultdict(set)
    skipped_long_author_papers = 0

    for paper in papers:
        paper_id = str(paper.get("paper_id") or "")
        source = str(paper.get("source") or "")
        year = _year_value(paper.get("year"))
        authors = [str(author).strip() for author in paper.get("authors") or [] if str(author).strip()]
        unique_authors = sorted(dict.fromkeys(authors))
        for index, author in enumerate(authors, start=1):
            paper_authors.append({"paper_id": paper_id, "source": source, "year": paper.get("year") or "", "author": author, "author_position": index})
            if year is not None:
                author_years[author][year] += 1
            author_fields[author][str(paper.get("field_seed") or paper.get("field") or "unknown")] += 1
        if len(unique_authors) > MAX_AUTHORS_FOR_CORE_NETWORK:
            skipped_long_author_papers += 1
        if len(unique_authors) < 2:
            continue
        pair_weight = 1 / math.comb(len(unique_authors), 2)
        author_weight = 1 / (len(unique_authors) - 1)
        for author_a, author_b in combinations(unique_authors, 2):
            key = (author_a, author_b)
            stats = edge_stats.setdefault(
                key,
                {
                    "author_a": author_a,
                    "author_b": author_b,
                    "paper_count": 0,
                    "weight_full": 0.0,
                    "weight_fraction_pair": 0.0,
                    "weight_fraction_author": 0.0,
                    "first_year": year,
                    "last_year": year,
                    "years": set(),
                    "long_author_papers": 0,
                },
            )
            stats["paper_count"] += 1
            stats["weight_full"] += 1.0
            stats["weight_fraction_pair"] += pair_weight
            stats["weight_fraction_author"] += author_weight
            if year is not None:
                stats["years"].add(year)
                stats["first_year"] = min([item for item in (stats["first_year"], year) if item is not None])
                stats["last_year"] = max([item for item in (stats["last_year"], year) if item is not None])
            if len(unique_authors) > MAX_AUTHORS_FOR_CORE_NETWORK:
                stats["long_author_papers"] += 1
            author_collaborators[author_a].add(author_b)
            author_collaborators[author_b].add(author_a)

    edge_rows: list[dict[str, Any]] = []
    graph = nx.Graph()
    for stats in edge_stats.values():
        row = {
            "author_a": stats["author_a"],
            "author_b": stats["author_b"],
            "weight": int(stats["paper_count"]),
            "paper_count": int(stats["paper_count"]),
            "weight_full": round(float(stats["weight_full"]), 6),
            "weight_fraction_pair": round(float(stats["weight_fraction_pair"]), 6),
            "weight_fraction_author": round(float(stats["weight_fraction_author"]), 6),
            "first_year": stats["first_year"] or "",
            "last_year": stats["last_year"] or "",
            "active_years": len(stats["years"]),
            "long_author_papers": int(stats["long_author_papers"]),
        }
        edge_rows.append(row)
        if int(stats["long_author_papers"]) == 0:
            weight = float(stats["weight_fraction_pair"])
            graph.add_edge(str(stats["author_a"]), str(stats["author_b"]), weight=weight, distance=1 / weight if weight else 1)
    edge_rows.sort(key=lambda row: (-float(row["weight_fraction_pair"]), -int(row["paper_count"]), row["author_a"], row["author_b"]))

    degree = dict(graph.degree(weight="weight")) if graph.number_of_nodes() else {}
    betweenness = nx.betweenness_centrality(graph, weight="distance", k=min(500, graph.number_of_nodes()), seed=42) if graph.number_of_nodes() > 1 else {}
    try:
        eigenvector = nx.eigenvector_centrality(graph, weight="weight", max_iter=300) if graph.number_of_nodes() > 1 else {}
    except nx.NetworkXException:
        eigenvector = {}

    metrics_rows: list[dict[str, Any]] = []
    for author in sorted(set(author_years).union(author_collaborators)):
        years = author_years.get(author, Counter())
        fields = author_fields.get(author, Counter())
        metrics_rows.append(
            {
                "author": author,
                "paper_count": sum(years.values()),
                "collaborator_count": len(author_collaborators.get(author, set())),
                "degree": round(float(degree.get(author, 0)), 6),
                "betweenness": round(float(betweenness.get(author, 0)), 6),
                "eigenvector": round(float(eigenvector.get(author, 0)), 6),
                "first_year": min(years) if years else "",
                "last_year": max(years) if years else "",
                "active_years": len(years),
                "dominant_field": fields.most_common(1)[0][0] if fields else "",
            }
        )
    metrics_rows.sort(key=lambda row: (-float(row["betweenness"]), -float(row["degree"]), -int(row["paper_count"]), row["author"]))

    by_year_rows = [
        {"author": author, "year": year, "paper_count": count}
        for author, years in sorted(author_years.items())
        for year, count in sorted(years.items())
    ]

    communities = []
    best_resolution = ""
    if graph.number_of_edges():
        best_score = (-1.0, 0)
        best_communities: list[set[str]] = []
        for resolution in (0.8, 1.0, 1.2):
            found = list(nx.algorithms.community.louvain_communities(graph, weight="weight", resolution=resolution, seed=42))
            modularity = nx.algorithms.community.modularity(graph, found, weight="weight") if found else 0.0
            score = (modularity, -abs(len(found) - math.sqrt(max(graph.number_of_nodes(), 1))))
            if score > best_score:
                best_score = score
                best_communities = [set(item) for item in found]
                best_resolution = str(resolution)
        for community_id, community in enumerate(best_communities):
            subgraph = graph.subgraph(community)
            top_authors = sorted(subgraph.degree(weight="weight"), key=lambda item: item[1], reverse=True)[:5]
            communities.append(
                {
                    "community_id": community_id,
                    "resolution": best_resolution,
                    "author_count": len(community),
                    "edge_count": subgraph.number_of_edges(),
                    "total_weight": round(sum(float(data.get("weight") or 0) for _, _, data in subgraph.edges(data=True)), 6),
                    "top_authors": "; ".join(author for author, _ in top_authors),
                }
            )
    communities.sort(key=lambda row: (-int(row["author_count"]), -float(row["total_weight"])))
    return paper_authors, edge_rows, metrics_rows, by_year_rows, communities


def _build_topic_assets(papers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    docs = [
        paper
        for paper in papers
        if _is_recent_year(paper.get("year")) and len(str(paper.get("text_for_analysis") or "").split()) >= 5
    ][:TOPIC_SAMPLE_LIMIT]
    if len(docs) < 2:
        return [], [], [], []
    try:
        from sklearn.decomposition import LatentDirichletAllocation, NMF
        from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
    except ImportError:
        return [], [], [], []

    texts = [str(paper.get("text_for_analysis") or "") for paper in docs]
    topic_count = max(2, min(8, len(docs) // 2))
    comparison_rows: list[dict[str, Any]] = []
    keyword_rows: list[dict[str, Any]] = []
    paper_topic_rows: list[dict[str, Any]] = []
    topic_year_counts: dict[tuple[str, int, int], int] = defaultdict(int)

    model_specs = [
        ("lda", CountVectorizer(max_features=1400, min_df=2, max_df=0.82, stop_words="english"), LatentDirichletAllocation(n_components=topic_count, random_state=42, learning_method="batch", max_iter=8)),
        ("nmf", TfidfVectorizer(max_features=1400, min_df=2, max_df=0.82, stop_words="english"), NMF(n_components=topic_count, random_state=42, init="nndsvda", max_iter=220)),
    ]
    for model_name, vectorizer, model in model_specs:
        try:
            matrix = vectorizer.fit_transform(texts)
            transformed = model.fit_transform(matrix)
        except ValueError:
            continue
        terms = vectorizer.get_feature_names_out()
        comparison_rows.append(
            {
                "model": model_name,
                "topics": topic_count,
                "documents": len(docs),
                "vocabulary": len(terms),
                "quality_proxy": round(float(getattr(model, "reconstruction_err_", 0) or getattr(model, "bound_", 0) or 0), 6),
            }
        )
        for topic_id, component in enumerate(model.components_):
            top_indices = np.argsort(component)[::-1][:12] if "np" in globals() else sorted(range(len(component)), key=lambda index: component[index], reverse=True)[:12]
            words = [str(terms[index]) for index in top_indices]
            keyword_rows.append({"model": model_name, "topic_id": topic_id, "ranked_keywords": "; ".join(words)})
        for paper, weights in zip(docs, transformed, strict=False):
            topic_id = int(max(range(len(weights)), key=lambda index: weights[index]))
            year = _year_value(paper.get("year"))
            if year is not None:
                topic_year_counts[(model_name, topic_id, year)] += 1
            if model_name == "nmf":
                paper_topic_rows.append(
                    {
                        "paper_id": paper.get("paper_id") or "",
                        "source": paper.get("source") or "",
                        "year": paper.get("year") or "",
                        "model": model_name,
                        "topic_id": topic_id,
                        "topic_weight": round(float(weights[topic_id]), 6),
                    }
                )
    topic_year_rows = [
        {"model": model, "topic_id": topic_id, "year": year, "paper_count": count}
        for (model, topic_id, year), count in sorted(topic_year_counts.items())
    ]
    return comparison_rows, keyword_rows, paper_topic_rows, topic_year_rows


def build_analysis_assets(
    *,
    raw_dir: str | Path = "data/raw",
    output_dir: str | Path = "data/analysis",
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    filename_template: str | None = None,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    papers: list[dict[str, Any]] = []
    seen: set[str] = set()
    input_records = 0
    duplicates = 0
    invalid_records = 0

    for wrapper in _iter_wrappers(raw_path, sources=sources, filename_template=filename_template):
        input_records += 1
        if wrapper is None:
            invalid_records += 1
            continue
        try:
            paper = _paper_with_source(wrapper)
        except (ValueError, TypeError, KeyError):
            invalid_records += 1
            continue
        key = _dedupe_key(paper, wrapper)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        papers.append(paper)

    paper_authors: list[dict[str, Any]] = []
    paper_keywords: list[dict[str, Any]] = []
    keyword_year_counts: Counter[tuple[str, int | str]] = Counter()
    edge_counts: Counter[tuple[str, str]] = Counter()

    for paper in papers:
        paper_id = str(paper.get("paper_id") or "")
        source = str(paper.get("source") or "")
        year = paper.get("year") or ""
        authors = [str(author).strip() for author in paper.get("authors") or [] if str(author).strip()]
        keywords = [str(keyword).strip() for keyword in paper.get("keywords") or [] if str(keyword).strip()]

        for index, author in enumerate(authors, start=1):
            paper_authors.append(
                {
                    "paper_id": paper_id,
                    "source": source,
                    "year": year,
                    "author": author,
                    "author_position": index,
                }
            )

        for keyword in keywords:
            row = {"paper_id": paper_id, "source": source, "year": year, "keyword": keyword}
            paper_keywords.append(row)
            if year:
                keyword_year_counts[(keyword, year)] += 1

        for author_a, author_b in combinations(sorted(set(authors)), 2):
            edge_counts[(author_a, author_b)] += 1

    keyword_year_rows = [
        {"keyword": keyword, "year": year, "count": count}
        for (keyword, year), count in sorted(keyword_year_counts.items(), key=lambda item: (str(item[0][0]), item[0][1]))
    ]
    edge_rows = [
        {"author_a": author_a, "author_b": author_b, "weight": weight}
        for (author_a, author_b), weight in sorted(edge_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    quality_by_source: dict[str, dict[str, int | str]] = defaultdict(
        lambda: {
            "source": "",
            "records": 0,
            "title_count": 0,
            "abstract_count": 0,
            "authors_count": 0,
            "year_count": 0,
            "keywords_count": 0,
            "full_text_count": 0,
        }
    )
    for paper in papers:
        source = str(paper.get("source") or "unknown")
        row = quality_by_source[source]
        row["source"] = source
        row["records"] = int(row["records"]) + 1
        row["title_count"] = int(row["title_count"]) + int(bool(paper.get("title")))
        row["abstract_count"] = int(row["abstract_count"]) + int(bool(paper.get("abstract")))
        row["authors_count"] = int(row["authors_count"]) + int(bool(paper.get("authors")))
        row["year_count"] = int(row["year_count"]) + int(bool(paper.get("year")))
        row["keywords_count"] = int(row["keywords_count"]) + int(bool(paper.get("keywords")))
        row["full_text_count"] = int(row["full_text_count"]) + int(bool(paper.get("full_text")))

    quality_rows = [quality_by_source[source] for source in sorted(quality_by_source)]

    output_path.joinpath("papers_clean.json").write_text(
        json.dumps(papers, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        output_path / "paper_authors.csv",
        paper_authors,
        ["paper_id", "source", "year", "author", "author_position"],
    )
    _write_csv(
        output_path / "paper_keywords.csv",
        paper_keywords,
        ["paper_id", "source", "year", "keyword"],
    )
    _write_csv(output_path / "keyword_year_matrix.csv", keyword_year_rows, ["keyword", "year", "count"])
    _write_csv(output_path / "author_collaboration_edges.csv", edge_rows, ["author_a", "author_b", "weight"])
    _write_csv(
        output_path / "source_quality_report.csv",
        quality_rows,
        [
            "source",
            "records",
            "title_count",
            "abstract_count",
            "authors_count",
            "year_count",
            "keywords_count",
            "full_text_count",
        ],
    )

    summary = {
        "input_records": input_records,
        "papers": len(papers),
        "duplicates": duplicates,
        "invalid_records": invalid_records,
        "sources": sorted({paper.get("source") for paper in papers if paper.get("source")}),
        "paper_authors": len(paper_authors),
        "paper_keywords": len(paper_keywords),
        "keyword_year_rows": len(keyword_year_rows),
        "author_edges": len(edge_rows),
    }
    output_path.joinpath("summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
