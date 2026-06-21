import json

import pytest

from src.harvest.fulltext_enrichment import enrich_fulltext_in_place
from src.harvest.normalize import normalize_raw_jsonl, openalex_work_to_paper, paper_wrapper_to_paper
from src.harvest.openalex_client import _query_params
from src.harvest.public_sources import (
    SUPPORTED_SOURCES,
    YEAR_SUPPORTED_SOURCES,
    _arxiv_search_query,
    _doaj_article_year,
    _year_query,
    _write_wrappers,
    default_raw_path,
    pmc_summary_record_to_item,
    year_raw_path,
)


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


def test_year_raw_path_separates_sources_years_and_limits():
    assert str(year_raw_path("openalex", 2024, 9000)) == "data/raw/openalex/openalex_2024_9000.jsonl"
    assert {"openalex", "arxiv", "pubmed", "pmc", "crossref", "doaj"} <= set(YEAR_SUPPORTED_SOURCES)


def test_public_source_year_queries_encode_source_specific_year_filters():
    assert _arxiv_search_query("large language model", year=2024) == (
        'all:"large language model" AND submittedDate:[202401010000 TO 202412312359]'
    )
    assert _year_query("cancer", 2023) == "(cancer) AND 2023[pdat]"


def test_doaj_article_year_reads_bibjson_year():
    assert _doaj_article_year({"bibjson": {"year": "2024"}}) == 2024
    assert _doaj_article_year({"bibjson": {"month": "2023-05"}}) == 2023


def test_openalex_query_params_can_filter_publication_year():
    params = _query_params(query="knowledge graph", cursor="*", per_page=200, year=2023)

    assert "has_abstract:true" in params["filter"]
    assert "from_publication_date:2023-01-01" in params["filter"]
    assert "to_publication_date:2023-12-31" in params["filter"]


def test_write_wrappers_keeps_existing_output_when_new_harvest_is_smaller(tmp_path):
    output = tmp_path / "raw.jsonl"
    old_lines = [
        json.dumps({"source_id": "old-1"}),
        json.dumps({"source_id": "old-2"}),
    ]
    output.write_text("\n".join(old_lines) + "\n", encoding="utf-8")

    def fetch_query(_field, _query, _limit):
        return [{"source_id": "new-1", "raw": {"title": "New Paper"}}]

    count = _write_wrappers(
        output_path=output,
        source="test",
        limit=1,
        fetch_query=fetch_query,
        queries=[("field", "query")],
    )

    assert count == 2
    assert output.read_text(encoding="utf-8") == "\n".join(old_lines) + "\n"
    assert not output.with_name("raw.jsonl.tmp").exists()


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


def test_arxiv_normalization_preserves_enriched_full_text():
    paper = paper_wrapper_to_paper(
        {
            "source": "arxiv",
            "source_id": "http://arxiv.org/abs/2401.00001v1",
            "field_seed": "computer science",
            "raw": {
                "id": "http://arxiv.org/abs/2401.00001v1",
                "title": "Agentic RAG for Scientific Discovery",
                "summary": "A survey of agentic retrieval workflows.",
                "authors": ["Ada Chen"],
                "published": "2024-01-01T00:00:00Z",
                "categories": ["cs.CL"],
                "body_excerpt": "Full arXiv source text excerpt.",
            },
        }
    )

    assert paper["full_text"] == "Full arXiv source text excerpt."


def test_doaj_normalization_preserves_enriched_full_text():
    paper = paper_wrapper_to_paper(
        {
            "source": "doaj",
            "source_id": "DOAJ-FT-1",
            "field_seed": "biomedicine",
            "raw": {
                "id": "DOAJ-FT-1",
                "bibjson": {
                    "title": "Visible browser full text",
                    "abstract": "Open access abstract.",
                    "author": [{"name": "Ada Chen"}],
                    "year": "2024",
                    "keywords": ["open access"],
                },
                "body_excerpt": "Browser extracted DOAJ full text.",
            },
        }
    )

    assert paper["full_text"] == "Browser extracted DOAJ full text."


def test_enrich_fulltext_updates_existing_arxiv_canonical_file_in_place(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    arxiv_dir = canonical_dir / "arxiv"
    arxiv_dir.mkdir(parents=True)
    path = arxiv_dir / "2024.jsonl"
    path.write_text(
        json.dumps(
            {
                "source": "arxiv",
                "source_id": "http://arxiv.org/abs/2401.00001v1",
                "raw": {
                    "id": "http://arxiv.org/abs/2401.00001v1",
                    "title": "Agentic RAG for Scientific Discovery",
                    "summary": "A survey.",
                    "authors": ["Ada Chen"],
                    "published": "2024-01-01T00:00:00Z",
                    "categories": ["cs.CL"],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "src.harvest.fulltext_enrichment._fetch_bytes",
        lambda _url, **_kwargs: b"\\section{Introduction} " + b"full text evidence " * 120,
    )
    monkeypatch.setattr("src.harvest.fulltext_enrichment.time.sleep", lambda _seconds: None)

    summary = enrich_fulltext_in_place(canonical_dir=canonical_dir, years=["2024"], limit=1)

    assert summary["records_enriched"] == 1
    assert list(arxiv_dir.glob("*.jsonl")) == [path]
    assert not path.with_name("2024.jsonl.tmp").exists()
    record = json.loads(path.read_text(encoding="utf-8"))
    assert "full text evidence" in record["raw"]["body_excerpt"]
    assert record["raw"]["full_text_source"] == "arxiv_eprint"


def test_enrich_fulltext_updates_doaj_fulltext_link_in_place(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    doaj_dir = canonical_dir / "doaj"
    doaj_dir.mkdir(parents=True)
    path = doaj_dir / "2024.jsonl"
    path.write_text(
        json.dumps(
            {
                "source": "doaj",
                "source_id": "doaj-1",
                "raw": {
                    "id": "doaj-1",
                    "bibjson": {
                        "title": "Open access retrieval systems",
                        "link": [
                            {
                                "type": "fulltext",
                                "content_type": "text/html",
                                "url": "https://example.org/fulltext",
                            }
                        ],
                    },
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "src.harvest.fulltext_enrichment._fetch_bytes",
        lambda _url, **_kwargs: b"<html><body><article><p>open access full text evidence </p>"
        + b"<p>retrieval systems and scientific agents </p>" * 90
        + b"</article></body></html>",
    )
    monkeypatch.setattr("src.harvest.fulltext_enrichment.time.sleep", lambda _seconds: None)

    summary = enrich_fulltext_in_place(canonical_dir=canonical_dir, source="doaj", years=["2024"], limit=1)

    assert summary["records_enriched"] == 1
    assert list(doaj_dir.glob("*.jsonl")) == [path]
    record = json.loads(path.read_text(encoding="utf-8"))
    assert "retrieval systems and scientific agents" in record["raw"]["body_excerpt"]
    assert record["raw"]["full_text_source"] == "doaj_fulltext_url"
    assert record["raw"]["full_text_url"] == "https://example.org/fulltext"


def test_enrich_fulltext_falls_back_to_browser_for_blocked_publisher(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    doaj_dir = canonical_dir / "doaj"
    doaj_dir.mkdir(parents=True)
    path = doaj_dir / "2024.jsonl"
    path.write_text(
        json.dumps(
            {
                "source": "doaj",
                "source_id": "mdpi-1",
                "raw": {
                    "id": "mdpi-1",
                    "bibjson": {
                        "title": "MDPI article with visible browser text",
                        "link": [
                            {
                                "type": "fulltext",
                                "content_type": "text/html",
                                "url": "https://www.mdpi.com/2073-4409/11/19/3007",
                            }
                        ],
                    },
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    def blocked_fetch(_url, **_kwargs):
        raise OSError("403 forbidden")

    monkeypatch.setattr("src.harvest.fulltext_enrichment._fetch_bytes", blocked_fetch)
    monkeypatch.setattr(
        "src.harvest.fulltext_enrichment._fetch_text_with_browser",
        lambda _url, **_kwargs: "browser extracted mdpi article body " * 800,
    )
    monkeypatch.setattr("src.harvest.fulltext_enrichment.time.sleep", lambda _seconds: None)

    summary = enrich_fulltext_in_place(canonical_dir=canonical_dir, source="doaj", years=["2024"], limit=1)

    assert summary["records_enriched"] == 1
    record = json.loads(path.read_text(encoding="utf-8"))
    assert "browser extracted mdpi article body" in record["raw"]["body_excerpt"]
    assert record["raw"]["full_text_source"] == "doaj_fulltext_url_browser"


def test_enrich_fulltext_checkpoint_writes_successes_before_year_finishes(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    doaj_dir = canonical_dir / "doaj"
    doaj_dir.mkdir(parents=True)
    path = doaj_dir / "2024.jsonl"
    records = [
        {
            "source": "doaj",
            "source_id": f"doaj-{index}",
            "raw": {
                "id": f"doaj-{index}",
                "bibjson": {
                    "title": f"Article {index}",
                    "link": [{"type": "fulltext", "url": f"https://example.org/{index}"}],
                },
            },
        }
        for index in range(2)
    ]
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")

    def fake_fetch(url, **_kwargs):
        if url.endswith("/1"):
            raise OSError("network failure")
        return b"<html><body><article>" + b"checkpoint full text " * 120 + b"</article></body></html>"

    monkeypatch.setattr("src.harvest.fulltext_enrichment._fetch_bytes", fake_fetch)
    monkeypatch.setattr("src.harvest.fulltext_enrichment.time.sleep", lambda _seconds: None)

    summary = enrich_fulltext_in_place(
        canonical_dir=canonical_dir,
        source="doaj",
        years=["2024"],
        limit=2,
        checkpoint_every=1,
    )

    persisted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert summary["records_enriched"] == 1
    assert "checkpoint full text" in persisted[0]["raw"]["body_excerpt"]


def test_enrich_fulltext_updates_crossref_fulltext_link_in_place(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    crossref_dir = canonical_dir / "crossref"
    crossref_dir.mkdir(parents=True)
    path = crossref_dir / "2024.jsonl"
    path.write_text(
        json.dumps(
            {
                "source": "crossref",
                "source_id": "10.5555/sciscope.1",
                "raw": {
                    "DOI": "10.5555/sciscope.1",
                    "link": [
                        {
                            "URL": "https://example.org/article.html",
                            "content-type": "text/html",
                            "intended-application": "text-mining",
                        }
                    ],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "src.harvest.fulltext_enrichment._fetch_bytes",
        lambda _url, **_kwargs: b"<html><body><main><p>crossref linked full text </p>"
        + b"<p>evidence for literature mining </p>" * 90
        + b"</main></body></html>",
    )
    monkeypatch.setattr("src.harvest.fulltext_enrichment.time.sleep", lambda _seconds: None)

    summary = enrich_fulltext_in_place(canonical_dir=canonical_dir, source="crossref", years=["2024"], limit=1)

    assert summary["records_enriched"] == 1
    assert list(crossref_dir.glob("*.jsonl")) == [path]
    record = json.loads(path.read_text(encoding="utf-8"))
    assert "evidence for literature mining" in record["raw"]["body_excerpt"]
    assert record["raw"]["full_text_source"] == "crossref_fulltext_url"


def test_enrich_fulltext_stops_after_max_attempts(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    crossref_dir = canonical_dir / "crossref"
    crossref_dir.mkdir(parents=True)
    path = crossref_dir / "2024.jsonl"
    records = [
        {
            "source": "crossref",
            "source_id": f"10.5555/sciscope.{index}",
            "raw": {
                "DOI": f"10.5555/sciscope.{index}",
                "link": [{"URL": f"https://example.org/{index}.html", "content-type": "text/html"}],
            },
        }
        for index in range(3)
    ]
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")

    def fail_fetch(_url, **_kwargs):
        raise OSError("network failure")

    monkeypatch.setattr("src.harvest.fulltext_enrichment._fetch_bytes", fail_fetch)

    summary = enrich_fulltext_in_place(
        canonical_dir=canonical_dir,
        source="crossref",
        years=["2024"],
        limit=2,
        max_attempts=2,
    )

    assert summary["records_seen"] == 2
    assert summary["records_enriched"] == 0
    assert summary["errors"] == 2


def test_enrich_fulltext_stable_only_skips_low_yield_domains(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    doaj_dir = canonical_dir / "doaj"
    doaj_dir.mkdir(parents=True)
    path = doaj_dir / "2024.jsonl"
    records = [
        {
            "source": "doaj",
            "source_id": "ieee-1",
            "raw": {
                "id": "ieee-1",
                "bibjson": {
                    "title": "IEEE landing page",
                    "link": [{"type": "fulltext", "url": "https://ieeexplore.ieee.org/document/9887960/"}],
                },
            },
        },
        {
            "source": "doaj",
            "source_id": "mdpi-1",
            "raw": {
                "id": "mdpi-1",
                "bibjson": {
                    "title": "MDPI full text",
                    "link": [{"type": "fulltext", "url": "https://www.mdpi.com/2073-4409/11/19/3007"}],
                },
            },
        },
    ]
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")

    fetched: list[str] = []

    def fake_fetch(url, **_kwargs):
        fetched.append(url)
        return b"<html><body><article>" + b"stable full text " * 120 + b"</article></body></html>"

    monkeypatch.setattr("src.harvest.fulltext_enrichment._fetch_bytes", fake_fetch)
    monkeypatch.setattr("src.harvest.fulltext_enrichment.time.sleep", lambda _seconds: None)

    summary = enrich_fulltext_in_place(
        canonical_dir=canonical_dir,
        source="doaj",
        years=["2024"],
        limit=1,
        stable_only=True,
    )

    assert summary["records_enriched"] == 1
    assert fetched == ["https://www.mdpi.com/2073-4409/11/19/3007"]


def test_enrich_fulltext_stable_only_resolves_openalex_doi(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "raw_canonical"
    openalex_dir = canonical_dir / "openalex"
    openalex_dir.mkdir(parents=True)
    path = openalex_dir / "2024.jsonl"
    path.write_text(
        json.dumps(
            {
                "source": "openalex",
                "source_id": "https://openalex.org/W1",
                "raw": {
                    "id": "https://openalex.org/W1",
                    "doi": "https://doi.org/10.3390/cells11193007",
                    "display_name": "MDPI article through DOI",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    fetched: list[str] = []

    monkeypatch.setattr(
        "src.harvest.fulltext_enrichment._resolve_redirect_url",
        lambda _url, **_kwargs: "https://www.mdpi.com/2073-4409/11/19/3007",
    )

    def fake_fetch(url, **_kwargs):
        fetched.append(url)
        return b"<html><body><article>" + b"resolved doi full text " * 120 + b"</article></body></html>"

    monkeypatch.setattr("src.harvest.fulltext_enrichment._fetch_bytes", fake_fetch)
    monkeypatch.setattr("src.harvest.fulltext_enrichment.time.sleep", lambda _seconds: None)

    summary = enrich_fulltext_in_place(
        canonical_dir=canonical_dir,
        source="openalex",
        years=["2024"],
        limit=1,
        stable_only=True,
    )

    record = json.loads(path.read_text(encoding="utf-8"))
    assert summary["records_enriched"] == 1
    assert fetched == ["https://www.mdpi.com/2073-4409/11/19/3007"]
    assert record["raw"]["full_text_url"] == "https://www.mdpi.com/2073-4409/11/19/3007"
    assert record["raw"]["full_text_source"] == "openalex_doi_url"


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

    assert stats == {"input_records": 1, "output_records": 1, "duplicates": 0, "invalid_records": 0}
    assert papers[0]["paper_id"] == "W123"


def test_normalize_raw_jsonl_skips_invalid_lines(tmp_path):
    raw_path = tmp_path / "works.jsonl"
    output_path = tmp_path / "papers.json"
    raw_path.write_text(
        json.dumps(_openalex_wrapper(), ensure_ascii=False) + "\n" + '{"source": "openalex", "raw": "truncated\n',
        encoding="utf-8",
    )

    stats = normalize_raw_jsonl(raw_path, output_path)
    papers = json.loads(output_path.read_text(encoding="utf-8"))

    assert stats == {"input_records": 2, "output_records": 1, "duplicates": 0, "invalid_records": 1}
    assert papers[0]["paper_id"] == "W123"
