import json

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
