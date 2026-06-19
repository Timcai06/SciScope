import json

from src.analysis.data_readiness import build_data_readiness_report


def test_build_data_readiness_report_quantifies_year_and_text_gaps(tmp_path):
    papers = [
        {
            "paper_id": "P1",
            "source": "pmc",
            "source_id": "PMC1",
            "title": "Paper 1",
            "abstract": "abstract",
            "authors": ["Ada Chen", "Lin Wang"],
            "year": 2022,
            "keywords": ["rag"],
            "field": "computer science",
            "full_text": "body",
        },
        {
            "paper_id": "P2",
            "source": "pubmed",
            "source_id": "2",
            "title": "Paper 2",
            "abstract": "",
            "authors": [],
            "year": 2026,
            "keywords": [],
            "field": "biomedicine",
            "full_text": "",
        },
    ]
    input_path = tmp_path / "papers_clean.json"
    output_path = tmp_path / "readiness.json"
    input_path.write_text(json.dumps(papers), encoding="utf-8")

    report = build_data_readiness_report(
        papers_path=input_path,
        output_path=output_path,
        target_per_year=10,
    )

    assert report["records"] == 2
    assert report["year_counts"]["2022"] == 1
    assert report["year_counts"]["2026"] == 1
    assert report["year_deficits_to_target"]["2023"] == 10
    assert report["text_coverage"]["full_text_records"] == 1
    assert report["rag_field_coverage"]["title"]["rate"] == 1
    assert output_path.exists()
