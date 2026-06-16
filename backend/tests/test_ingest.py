import csv
import json

from data_pipeline.loaders import load_papers
from data_pipeline.normalize import normalize_keyword, normalize_paper
from data_pipeline.sample_data import sample_papers_path


def test_sample_data_exists():
    path = sample_papers_path()
    assert path.exists()
    assert path.name == "papers.sample.json"


def test_sample_data_has_expected_shape():
    data = json.loads(sample_papers_path().read_text(encoding="utf-8"))

    assert isinstance(data, list)
    assert len(data) == 5
    assert [record["paper_id"] for record in data] == ["P001", "P002", "P003", "P004", "P005"]

    expected_keys = {
        "paper_id",
        "title",
        "abstract",
        "authors",
        "year",
        "keywords",
        "field",
        "full_text",
    }
    assert all(expected_keys <= record.keys() for record in data)
    assert data[1]["title"] == "Large Language Models for Knowledge Graph Reasoning"
    assert "knowledge graph" in data[1]["keywords"]


def test_load_papers_from_json():
    papers = load_papers(sample_papers_path())
    assert len(papers) == 5
    assert papers[0]["paper_id"] == "P001"
    assert "graph neural network" in papers[0]["keywords"]


def test_normalize_keyword():
    assert normalize_keyword(" Graph Neural Network ") == "graph neural network"
    assert normalize_keyword("Large-Language Model") == "large language model"


def test_normalize_paper_defaults():
    raw = {
        "paper_id": "X1",
        "title": " Test Title ",
        "abstract": " Test abstract ",
        "authors": "Alice; Bob",
        "year": "2024",
        "keywords": "AI; RAG",
        "field": "",
        "full_text": None,
    }
    paper = normalize_paper(raw)
    assert paper["title"] == "Test Title"
    assert paper["authors"] == ["Alice", "Bob"]
    assert paper["year"] == 2024
    assert paper["keywords"] == ["ai", "rag"]
    assert paper["field"] == "unknown"
    assert paper["full_text"] == ""


def test_normalize_paper_does_not_split_author_commas():
    paper = normalize_paper(
        {
            "paper_id": "X2",
            "title": "Comma Authors",
            "authors": "Smith, John; Doe, Jane",
        }
    )

    assert paper["authors"] == ["Smith, John", "Doe, Jane"]


def test_normalize_paper_none_required_text_fields_are_empty_strings():
    paper = normalize_paper({"paper_id": None, "title": None})

    assert paper["paper_id"] == ""
    assert paper["title"] == ""


def test_load_papers_from_csv_preserves_quoted_author_commas(tmp_path):
    path = tmp_path / "papers.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "paper_id",
                "title",
                "abstract",
                "authors",
                "year",
                "keywords",
                "field",
                "full_text",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "paper_id": "CSV1",
                "title": "Quoted Author Commas",
                "abstract": "",
                "authors": "Smith, John; Doe, Jane",
                "year": "2024",
                "keywords": "AI,RAG",
                "field": "",
                "full_text": "",
            }
        )

    papers = load_papers(path)

    assert papers[0]["authors"] == ["Smith, John", "Doe, Jane"]
    assert papers[0]["keywords"] == ["ai", "rag"]
