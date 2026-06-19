import json

import pytest

from src.harvest.normalize import normalize_raw_jsonl, openalex_work_to_paper, paper_wrapper_to_paper
from src.harvest.public_sources import SUPPORTED_SOURCES, default_raw_path, pmc_summary_record_to_item


def _openalex_wrapper():
    return {
        "source": "openalex",
        "source_id": "https://openalex.org/W123",
        "query": "retrieval augmented generation",
        "field_seed": "computer science",
        "raw": {
            "id": "https://openalex.org/W123",
            "display_name": "Retrieval Augmented Generation for Scientific Literature",
            "publication_year": 2024,
            "abstract_inverted_index": {
                "Retrieval": [0],
                "augmented": [1],
                "generation": [2],
                "supports": [3],
                "evidence": [4],
                "grounded": [5],
                "answers": [6],
            },
            "authorships": [
                {"author": {"display_name": "Ada Chen"}},
                {"author": {"display_name": "Lin Wang"}},
            ],
            "keywords": [{"display_name": "Retrieval Augmented Generation"}],
            "concepts": [{"display_name": "Information Retrieval", "score": 0.91}],
            "primary_topic": {
                "display_name": "Scientific Question Answering",
                "domain": {"display_name": "Computer Science"},
            },
        },
    }


@pytest.mark.parametrize(
    ("source", "wrapper", "expected_id", "expected_keyword"),
    [
        (
            "arxiv",
            {
                "source": "arxiv",
                "source_id": "http://arxiv.org/abs/2401.00001v1",
                "field_seed": "computer science",
                "raw": {
                    "id": "http://arxiv.org/abs/2401.00001v1",
                    "title": "Agentic RAG for Scientific Discovery",
                    "summary": "A survey of agentic retrieval workflows.",
                    "authors": ["Ada Chen", "Lin Wang"],
                    "published": "2024-01-01T00:00:00Z",
                    "categories": ["cs.CL", "cs.AI"],
                },
            },
            "2401.00001",
            "cs.cl",
        ),
        (
            "pubmed",
            {
                "source": "pubmed",
                "source_id": "39000001",
                "field_seed": "biomedicine",
                "raw": {
                    "pmid": "39000001",
                    "title": "Biomedical Large Language Models",
                    "abstract": "Clinical retrieval improves evidence synthesis.",
                    "authors": ["Mina Patel"],
                    "year": "2024",
                    "keywords": ["biomedical NLP"],
                    "journal": "Journal of Biomedical AI",
                },
            },
            "39000001",
            "biomedical nlp",
        ),
        (
            "pmc",
            {
                "source": "pmc",
                "source_id": "PMC123456",
                "field_seed": "biomedicine",
                "raw": {
                    "pmcid": "PMC123456",
                    "title": "Open Access Clinical Knowledge Graphs",
                    "abstract": "Knowledge graphs connect entities and trials.",
                    "authors": ["Jane Doe"],
                    "year": 2023,
                    "keywords": ["knowledge graph"],
                    "body_excerpt": "Partial full text excerpt.",
                },
            },
            "PMC123456",
            "knowledge graph",
        ),
        (
            "crossref",
            {
                "source": "crossref",
                "source_id": "10.5555/sciscope.1",
                "field_seed": "materials science",
                "raw": {
                    "DOI": "10.5555/sciscope.1",
                    "title": ["Materials Discovery with Transformers"],
                    "abstract": "<jats:p>Transformers accelerate materials screening.</jats:p>",
                    "author": [{"given": "Kai", "family": "Li"}],
                    "issued": {"date-parts": [[2022, 5, 1]]},
                    "subject": ["materials informatics"],
                },
            },
            "10.5555/sciscope.1",
            "materials informatics",
        ),
        (
            "semantic_scholar",
            {
                "source": "semantic_scholar",
                "source_id": "S2-1",
                "field_seed": "computer science",
                "raw": {
                    "paperId": "S2-1",
                    "title": "GraphRAG over Scientific Corpora",
                    "abstract": "Graph-aware retrieval improves provenance.",
                    "authors": [{"name": "Sam Lee"}],
                    "year": 2025,
                    "fieldsOfStudy": ["Computer Science"],
                    "s2FieldsOfStudy": [{"category": "Computer Science"}],
                },
            },
            "S2-1",
            "computer science",
        ),
        (
            "doaj",
            {
                "source": "doaj",
                "source_id": "DOAJ-1",
                "field_seed": "materials science",
                "raw": {
                    "id": "DOAJ-1",
                    "bibjson": {
                        "title": "Open Journal Catalysis Discovery",
                        "abstract": "Catalyst papers reveal emerging synthesis routes.",
                        "author": [{"name": "Rui Zhao"}],
                        "year": "2021",
                        "keywords": ["catalyst discovery"],
                        "subject": [{"term": "Materials Science"}],
                    },
                },
            },
            "DOAJ-1",
            "catalyst discovery",
        ),
        (
            "core",
            {
                "source": "core",
                "source_id": "core-1",
                "field_seed": "computer science",
                "raw": {
                    "id": "core-1",
                    "title": "Open Repository Paper Recommendation",
                    "abstract": "Repository metadata supports recommendation.",
                    "authors": [{"name": "Nora Smith"}],
                    "yearPublished": 2020,
                    "topics": ["paper recommendation"],
                },
            },
            "core-1",
            "paper recommendation",
        ),
    ],
)
def test_paper_wrapper_to_paper_supports_public_sources(source, wrapper, expected_id, expected_keyword):
    assert source in SUPPORTED_SOURCES

    paper = paper_wrapper_to_paper(wrapper)

    assert paper["paper_id"] == expected_id
    assert paper["title"]
    assert paper["abstract"]
    assert paper["authors"]
    assert paper["year"]
    assert expected_keyword in paper["keywords"]


def test_default_raw_path_separates_sources_and_limits():
    assert str(default_raw_path("arxiv", 500)) == "data/raw/arxiv/arxiv_500.jsonl"


def test_pmc_summary_record_to_item_preserves_metadata_when_full_text_is_unavailable():
    item = pmc_summary_record_to_item(
        {
            "uid": "123456",
            "title": "Machine learning in oncology",
            "pubdate": "2024 Jan",
            "fulljournalname": "Open Oncology",
            "authors": [{"name": "Ada Chen"}, {"name": "Lin Wang"}],
            "articleids": [{"idtype": "pmc", "value": "PMC123456"}, {"idtype": "doi", "value": "10.5555/pmc.1"}],
        }
    )

    assert item["source_id"] == "PMC123456"
    assert item["raw"]["title"] == "Machine learning in oncology"
    assert item["raw"]["year"] == "2024"
    assert item["raw"]["authors"] == ["Ada Chen", "Lin Wang"]
    assert item["raw"]["doi"] == "10.5555/pmc.1"


def test_openalex_work_to_paper_restores_abstract_and_metadata():
    paper = openalex_work_to_paper(_openalex_wrapper())

    assert paper["paper_id"] == "W123"
    assert paper["title"] == "Retrieval Augmented Generation for Scientific Literature"
    assert paper["abstract"] == "Retrieval augmented generation supports evidence grounded answers"
    assert paper["authors"] == ["Ada Chen", "Lin Wang"]
    assert paper["year"] == 2024
    assert "retrieval augmented generation" in paper["keywords"]
    assert paper["field"] == "computer science"


def test_normalize_raw_jsonl_writes_processed_json(tmp_path):
    raw_path = tmp_path / "works.jsonl"
    output_path = tmp_path / "papers.json"
    raw_path.write_text(json.dumps(_openalex_wrapper(), ensure_ascii=False) + "\n", encoding="utf-8")

    stats = normalize_raw_jsonl(raw_path, output_path)
    papers = json.loads(output_path.read_text(encoding="utf-8"))

    assert stats == {"input_records": 1, "output_records": 1, "duplicates": 0}
    assert papers[0]["paper_id"] == "W123"
