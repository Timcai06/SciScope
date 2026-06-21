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
        analysis_dir / "author_collaboration_edges.csv",
        [
            {"author_a": "Ada Chen", "author_b": "Lin Wang", "weight": 2},
            {"author_a": "Ada Chen", "author_b": "Bo Li", "weight": 1},
        ],
        ["author_a", "author_b", "weight"],
    )

    summary = build_report_figures(analysis_dir=analysis_dir, output_dir=output_dir)

    assert summary["figures"] == 13
    manifest = list(csv.DictReader((output_dir / "figure_manifest.csv").open(encoding="utf-8")))
    assert len(manifest) == 13
    assert {row["figure_id"] for row in manifest} >= {
        "field_distribution",
        "field_year_heatmap",
        "source_quality",
        "source_year_heatmap",
        "keyword_evolution",
        "keyword_momentum",
        "author_network_scale",
        "author_communities",
        "top_author_collaborations",
    }
    text_coverage = next(row for row in manifest if row["figure_id"] == "text_coverage")
    assert "Full-text records" in text_coverage["message"]
    assert "1" in text_coverage["message"]
    for row in manifest:
        assert (output_dir / row["file"]).exists()
