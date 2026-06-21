import csv
import json

from src.analysis.figures import build_report_figures


def _write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_build_report_figures_creates_manifest_and_pdf_assets(tmp_path):
    analysis_dir = tmp_path / "analysis"
    output_dir = tmp_path / "assets"
    analysis_dir.mkdir()
    analysis_dir.joinpath("papers_clean.json").write_text(
        json.dumps(
            [
                {"paper_id": "P1", "source": "pubmed", "year": 2023},
                {"paper_id": "P2", "source": "pubmed", "year": 2024},
                {"paper_id": "P3", "source": "doaj", "year": 2024},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_csv(
        analysis_dir / "source_quality_report.csv",
        [
            {
                "source": "pubmed",
                "records": 2,
                "title_count": 2,
                "abstract_count": 2,
                "authors_count": 2,
                "year_count": 2,
                "keywords_count": 1,
                "full_text_count": 1,
            },
            {
                "source": "doaj",
                "records": 1,
                "title_count": 1,
                "abstract_count": 1,
                "authors_count": 1,
                "year_count": 1,
                "keywords_count": 1,
                "full_text_count": 0,
            },
        ],
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
    _write_csv(
        analysis_dir / "paper_keywords.csv",
        [
            {"paper_id": "P1", "source": "pubmed", "year": 2023, "keyword": "rag"},
            {"paper_id": "P2", "source": "pubmed", "year": 2024, "keyword": "rag"},
            {"paper_id": "P3", "source": "doaj", "year": 2024, "keyword": "knowledge graph"},
        ],
        ["paper_id", "source", "year", "keyword"],
    )
    _write_csv(
        analysis_dir / "keyword_year_matrix.csv",
        [
            {"keyword": "rag", "year": 2023, "count": 1},
            {"keyword": "rag", "year": 2024, "count": 1},
            {"keyword": "knowledge graph", "year": 2024, "count": 1},
        ],
        ["keyword", "year", "count"],
    )
    _write_csv(
        analysis_dir / "keyword_cooccurrence_edges.csv",
        [
            {"keyword_a": "knowledge graph", "keyword_b": "rag", "weight": 3.0, "paper_count": 3},
            {"keyword_a": "clinical search", "keyword_b": "rag", "weight": 2.0, "paper_count": 2},
            {"keyword_a": "knowledge graph", "keyword_b": "question answering", "weight": 1.5, "paper_count": 2},
        ],
        ["keyword_a", "keyword_b", "weight", "paper_count"],
    )
    _write_csv(
        analysis_dir / "keyword_metrics.csv",
        [
            {"keyword": "rag", "doc_count": 5, "weighted_degree": 5.0, "pagerank": 0.4, "community_id": 0, "lifecycle_stage": "growth"},
            {"keyword": "knowledge graph", "doc_count": 4, "weighted_degree": 4.5, "pagerank": 0.3, "community_id": 0, "lifecycle_stage": "maturity"},
            {"keyword": "clinical search", "doc_count": 2, "weighted_degree": 2.0, "pagerank": 0.15, "community_id": 1, "lifecycle_stage": "emergence"},
            {"keyword": "question answering", "doc_count": 2, "weighted_degree": 1.5, "pagerank": 0.15, "community_id": 1, "lifecycle_stage": "growth"},
        ],
        ["keyword", "doc_count", "weighted_degree", "pagerank", "community_id", "lifecycle_stage"],
    )
    _write_csv(
        analysis_dir / "keyword_lifecycle.csv",
        [
            {"keyword": "rag", "lifecycle_stage": "growth", "doc_count": 5, "first_year": 2023, "peak_year": 2024, "last_year": 2024},
            {"keyword": "knowledge graph", "lifecycle_stage": "maturity", "doc_count": 4, "first_year": 2023, "peak_year": 2024, "last_year": 2024},
        ],
        ["keyword", "lifecycle_stage", "doc_count", "first_year", "peak_year", "last_year"],
    )
    _write_csv(
        analysis_dir / "keyword_burst_windows.csv",
        [
            {"keyword": "rag", "year": 2024, "growth_rate": 1.5, "burst_score": 2.2, "burst_state": "growth"},
            {"keyword": "knowledge graph", "year": 2024, "growth_rate": 1.2, "burst_score": 1.8, "burst_state": "growth"},
        ],
        ["keyword", "year", "growth_rate", "burst_score", "burst_state"],
    )
    _write_csv(
        analysis_dir / "author_collaboration_edges.csv",
        [
            {
                "author_a_key": "name:ada",
                "author_b_key": "name:lin",
                "author_a": "Ada Chen",
                "author_b": "Lin Wang",
                "weight": 5,
                "paper_count": 5,
                "weight_fraction_pair": 3.5,
            },
            {
                "author_a_key": "name:ada",
                "author_b_key": "name:bo",
                "author_a": "Ada Chen",
                "author_b": "Bo Li",
                "weight": 4,
                "paper_count": 4,
                "weight_fraction_pair": 2.5,
            },
            {
                "author_a_key": "name:cam",
                "author_b_key": "name:dee",
                "author_a": "Cam Zhao",
                "author_b": "Dee Sun",
                "weight": 3,
                "paper_count": 3,
                "weight_fraction_pair": 2.0,
            },
        ],
        ["author_a_key", "author_b_key", "author_a", "author_b", "weight", "paper_count", "weight_fraction_pair"],
    )
    _write_csv(
        analysis_dir / "author_metrics.csv",
        [
            {
                "author_key": "name:ada",
                "author": "Ada Chen",
                "paper_count": 3,
                "collaborator_count": 2,
                "degree": 6.0,
                "betweenness": 0.4,
                "eigenvector": 0.7,
                "pagerank": 0.5,
                "core_number": 2,
                "community_id": 0,
                "dominant_field": "computer science",
            },
            {
                "author_key": "name:lin",
                "author": "Lin Wang",
                "paper_count": 2,
                "collaborator_count": 1,
                "degree": 3.5,
                "betweenness": 0.1,
                "eigenvector": 0.5,
                "pagerank": 0.3,
                "core_number": 1,
                "community_id": 0,
                "dominant_field": "computer science",
            },
            {
                "author_key": "name:bo",
                "author": "Bo Li",
                "paper_count": 2,
                "collaborator_count": 1,
                "degree": 2.5,
                "betweenness": 0.1,
                "eigenvector": 0.4,
                "pagerank": 0.2,
                "core_number": 1,
                "community_id": 1,
                "dominant_field": "computer science",
            },
            {
                "author_key": "name:cam",
                "author": "Cam Zhao",
                "paper_count": 2,
                "collaborator_count": 1,
                "degree": 2.0,
                "betweenness": 0.0,
                "eigenvector": 0.3,
                "pagerank": 0.2,
                "core_number": 1,
                "community_id": 2,
                "dominant_field": "materials",
            },
            {
                "author_key": "name:dee",
                "author": "Dee Sun",
                "paper_count": 2,
                "collaborator_count": 1,
                "degree": 2.0,
                "betweenness": 0.0,
                "eigenvector": 0.3,
                "pagerank": 0.2,
                "core_number": 1,
                "community_id": 2,
                "dominant_field": "materials",
            },
        ],
        [
            "author_key",
            "author",
            "paper_count",
            "collaborator_count",
            "degree",
            "betweenness",
            "eigenvector",
            "pagerank",
            "core_number",
            "community_id",
            "dominant_field",
        ],
    )

    summary = build_report_figures(analysis_dir=analysis_dir, output_dir=output_dir)

    assert summary["figures"] == 17
    manifest = list(csv.DictReader((output_dir / "figure_manifest.csv").open(encoding="utf-8")))
    assert len(manifest) == 17
    assert {row["figure_id"] for row in manifest} >= {
        "field_distribution",
        "field_year_heatmap",
        "source_quality",
        "source_year_heatmap",
        "keyword_evolution",
        "keyword_momentum",
        "keyword_cooccurrence_network",
        "keyword_lifecycle",
        "keyword_burst_windows",
        "author_network_scale",
        "author_core_network",
        "author_component_overview",
        "top_author_collaborations",
    }
    author_graph = next(row for row in manifest if row["figure_id"] == "author_core_network")
    assert author_graph["source_table"] == "author_collaboration_edges.csv;author_metrics.csv"
    component_graph = next(row for row in manifest if row["figure_id"] == "author_component_overview")
    assert component_graph["source_table"] == "author_collaboration_edges.csv;author_metrics.csv"
    assert "component" in component_graph["message"]
    top_collaborations = next(row for row in manifest if row["figure_id"] == "top_author_collaborations")
    assert top_collaborations["source_table"] == "author_collaboration_edges.csv"
    text_coverage = next(row for row in manifest if row["figure_id"] == "text_coverage")
    assert "Full-text records" in text_coverage["message"]
    assert "1" in text_coverage["message"]
    for row in manifest:
        assert (output_dir / row["file"]).exists()
