import csv
import json

from src.analysis.assets import build_analysis_assets


def _wrapper(source_id: str, *, title: str, year: int, authors: list[str], keywords: list[str], source: str = "pubmed"):
    if source == "doaj":
        raw = {
            "id": source_id,
            "bibjson": {
                "title": title,
                "abstract": f"{title} abstract",
                "author": [{"name": author} for author in authors],
                "year": str(year),
                "keywords": keywords,
            },
        }
    else:
        raw = {
            "pmid": source_id,
            "id": source_id,
            "title": title,
            "abstract": f"{title} abstract",
            "authors": authors,
            "year": year,
            "keywords": keywords,
        }
    return {
        "source": source,
        "source_id": source_id,
        "query": "retrieval augmented generation",
        "field_seed": "computer science",
        "raw": raw,
    }


def _openalex_wrapper(
    source_id: str,
    *,
    title: str,
    year: int,
    authorships: list[dict],
    keywords: list[str] | None = None,
):
    return {
        "source": "openalex",
        "source_id": f"https://openalex.org/{source_id}",
        "query": "knowledge graph",
        "field_seed": "computer science",
        "raw": {
            "id": f"https://openalex.org/{source_id}",
            "display_name": title,
            "publication_year": year,
            "authorships": authorships,
            "keywords": [{"display_name": keyword} for keyword in (keywords or ["Knowledge Graph"])],
        },
    }


def _openalex_authorship(
    author_id: str,
    display_name: str,
    *,
    raw_author_name: str | None = None,
    orcid: str | None = None,
    institution_id: str | None = None,
    institution_name: str | None = None,
    country_code: str | None = None,
    position: str = "middle",
):
    institution = (
        {
            "id": institution_id,
            "display_name": institution_name,
            "country_code": country_code,
        }
        if institution_id
        else {}
    )
    return {
        "author": {
            "id": f"https://openalex.org/{author_id}",
            "display_name": display_name,
            "orcid": orcid,
        },
        "raw_author_name": raw_author_name or display_name,
        "raw_orcid": orcid,
        "author_position": position,
        "is_corresponding": position == "first",
        "institutions": [institution] if institution else [],
        "countries": [country_code] if country_code else [],
        "raw_affiliation_strings": [institution_name] if institution_name else [],
    }


def _read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_analysis_assets_creates_report_ready_tables(tmp_path):
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "analysis"
    pubmed_dir = raw_dir / "pubmed"
    doaj_dir = raw_dir / "doaj"
    pubmed_dir.mkdir(parents=True)
    doaj_dir.mkdir(parents=True)
    pubmed_records = [
        _wrapper("P1", title="RAG for Literature Review", year=2024, authors=["Ada Chen", "Lin Wang"], keywords=["RAG", "AI"]),
        _wrapper("P1", title="RAG for Literature Review", year=2024, authors=["Ada Chen"], keywords=["RAG"]),
    ]
    doaj_records = [
        _wrapper(
            "D1",
            title="Knowledge Graph Discovery",
            year=2025,
            authors=["Ada Chen", "Bo Li"],
            keywords=["RAG", "Knowledge Graph"],
            source="doaj",
        )
    ]
    pubmed_dir.joinpath("pubmed_2.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in pubmed_records) + "\n",
        encoding="utf-8",
    )
    doaj_dir.joinpath("doaj_1.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in doaj_records) + "\n",
        encoding="utf-8",
    )

    summary = build_analysis_assets(raw_dir=raw_dir, output_dir=output_dir)

    assert summary["input_records"] == 3
    assert summary["papers"] == 2
    assert summary["duplicates"] == 1
    assert summary["invalid_records"] == 0
    assert set(summary["sources"]) == {"pubmed", "doaj"}

    papers = json.loads(output_dir.joinpath("papers_clean.json").read_text(encoding="utf-8"))
    assert [paper["paper_id"] for paper in papers] == ["P1", "D1"]
    assert papers[0]["source"] == "pubmed"
    assert papers[1]["source"] == "doaj"

    authors = _read_csv(output_dir / "paper_authors.csv")
    assert {row["author"] for row in authors} == {"Ada Chen", "Lin Wang", "Bo Li"}
    assert authors[0]["author_position"] == "1"

    keywords = _read_csv(output_dir / "paper_keywords.csv")
    assert {row["keyword"] for row in keywords} == {"artificial intelligence", "retrieval augmented generation", "knowledge graph"}

    keyword_signals = _read_csv(output_dir / "paper_keyword_signals.csv")
    assert any(row["keyword"] == "retrieval augmented generation" and row["signal_source"] == "title_abstract" for row in keyword_signals)
    assert any(row["keyword"] == "retrieval augmented generation" and row["signal_source"] == "explicit_keyword" for row in keyword_signals)

    keyword_year = _read_csv(output_dir / "keyword_year_matrix.csv")
    assert any(
        row["keyword"] == "retrieval augmented generation"
        and row["year"] == "2024"
        and row["count"] == "1"
        and row["explicit_count"] == "1"
        and row["text_signal_count"] == "1"
        and row["total_docs_in_year"] == "1"
        and row["analyzable_docs_in_year"] == "1"
        and row["normalized_df"] == "1.0"
        for row in keyword_year
    )
    assert any(
        row["keyword"] == "retrieval augmented generation"
        and row["year"] == "2025"
        and row["count"] == "1"
        and row["explicit_count"] == "1"
        and row["text_signal_count"] == "0"
        and row["total_docs_in_year"] == "1"
        and row["analyzable_docs_in_year"] == "1"
        and row["normalized_df"] == "1.0"
        for row in keyword_year
    )

    edges = _read_csv(output_dir / "author_collaboration_edges.csv")
    assert {"author_a": "Ada Chen", "author_b": "Lin Wang", "weight": "1", "paper_count": "1"} in [
        {key: row[key] for key in ("author_a", "author_b", "weight", "paper_count")} for row in edges
    ]
    assert {"author_a": "Ada Chen", "author_b": "Bo Li", "weight": "1", "paper_count": "1"} in [
        {key: row[key] for key in ("author_a", "author_b", "weight", "paper_count")} for row in edges
    ]

    quality = _read_csv(output_dir / "source_quality_report.csv")
    pubmed_quality = next(row for row in quality if row["source"] == "pubmed")
    assert pubmed_quality["records"] == "1"
    assert pubmed_quality["abstract_count"] == "1"

    saved_summary = json.loads(output_dir.joinpath("summary.json").read_text(encoding="utf-8"))
    assert saved_summary == summary


def test_build_analysis_assets_outputs_trend_network_and_topic_layers(tmp_path):
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "analysis"
    pubmed_dir = raw_dir / "pubmed"
    pubmed_dir.mkdir(parents=True)
    rows = [
        _wrapper(
            "A1",
            title="Retrieval-Augmented Generation for Clinical Search",
            year=2022,
            authors=["Ada Chen", "Lin Wang", "Mira Zhao"],
            keywords=["Retrieval-Augmented Generation", "Clinical Search"],
        ),
        _wrapper(
            "A2",
            title="Retrieval Augmented Generation for Biomedical Question Answering",
            year=2025,
            authors=["Ada Chen", "Bo Li"],
            keywords=["retrieval augmented generation", "Question Answering"],
        ),
        _wrapper(
            "A3",
            title="Graph Neural Networks for Catalyst Discovery",
            year=2025,
            authors=["Nia Kumar", "Omar Singh"],
            keywords=["Graph neural networks", "Catalyst Discovery"],
        ),
    ]
    pubmed_dir.joinpath("pubmed.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in rows) + "\n",
        encoding="utf-8",
    )

    summary = build_analysis_assets(raw_dir=raw_dir, output_dir=output_dir, sources=("pubmed",))

    assert summary["collection_files"] == 1
    manifest = _read_csv(output_dir / "collection_manifest.csv")
    assert manifest[0]["records"] == "3"
    assert manifest[0]["empty_file"] == "False"

    trends = _read_csv(output_dir / "keyword_trends.csv")
    rag = next(row for row in trends if row["keyword"] == "retrieval augmented generation")
    assert rag["doc_count"] == "2"
    assert float(rag["normalized_df_2025"]) == 0.5
    assert rag["representative_paper_id"] == "A2"

    edges = _read_csv(output_dir / "author_collaboration_edges.csv")
    ada_lin = next(row for row in edges if row["author_a"] == "Ada Chen" and row["author_b"] == "Lin Wang")
    assert ada_lin["paper_count"] == "1"
    assert round(float(ada_lin["weight_fraction_pair"]), 6) == 0.333333
    assert ada_lin["first_year"] == "2022"

    metrics = _read_csv(output_dir / "author_metrics.csv")
    assert "betweenness" in metrics[0]
    assert any(row["author"] == "Ada Chen" for row in metrics)

    comparison = _read_csv(output_dir / "topic_model_comparison.csv")
    assert {row["model"] for row in comparison} == {"lda", "nmf"}
    topic_keywords = _read_csv(output_dir / "topic_keywords.csv")
    assert topic_keywords


def test_build_analysis_assets_preserves_openalex_author_identity_and_affiliations(tmp_path):
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "analysis"
    openalex_dir = raw_dir / "openalex"
    openalex_dir.mkdir(parents=True)
    rows = [
        _openalex_wrapper(
            "W1",
            title="Knowledge Graph Paper One",
            year=2024,
            authorships=[
                _openalex_authorship(
                    "A1",
                    "Rui Zhang",
                    raw_author_name="Zhang, Rui",
                    orcid="https://orcid.org/0000-0001-0000-0001",
                    institution_id="https://openalex.org/I1",
                    institution_name="Alpha University",
                    country_code="US",
                    position="first",
                ),
                _openalex_authorship(
                    "A2",
                    "Ada Chen",
                    institution_id="https://openalex.org/I2",
                    institution_name="Beta Lab",
                    country_code="CN",
                    position="last",
                ),
            ],
        ),
        _openalex_wrapper(
            "W2",
            title="Knowledge Graph Paper Two",
            year=2024,
            authorships=[
                _openalex_authorship(
                    "A3",
                    "Rui Zhang",
                    raw_author_name="R. Zhang",
                    institution_id="https://openalex.org/I3",
                    institution_name="Gamma Institute",
                    country_code="GB",
                    position="first",
                ),
                _openalex_authorship("A4", "Bo Li", position="last"),
            ],
        ),
    ]
    openalex_dir.joinpath("openalex.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in rows) + "\n",
        encoding="utf-8",
    )

    summary = build_analysis_assets(raw_dir=raw_dir, output_dir=output_dir, sources=("openalex",))

    assert summary["papers"] == 2
    authors = _read_csv(output_dir / "paper_authors.csv")
    rui_rows = [row for row in authors if row["author"] == "Rui Zhang"]
    assert {row["author_key"] for row in rui_rows} == {"https://openalex.org/A1", "https://openalex.org/A3"}
    assert rui_rows[0]["raw_author_name"] == "Zhang, Rui"
    assert rui_rows[0]["orcid"] == "https://orcid.org/0000-0001-0000-0001"
    assert rui_rows[0]["institution_ids"] == "https://openalex.org/I1"
    assert rui_rows[0]["institutions"] == "Alpha University"
    assert rui_rows[0]["country_codes"] == "US"

    edges = _read_csv(output_dir / "author_collaboration_edges.csv")
    edge_keys = {(row["author_a_key"], row["author_b_key"]) for row in edges}
    assert ("https://openalex.org/A1", "https://openalex.org/A2") in edge_keys
    assert ("https://openalex.org/A3", "https://openalex.org/A4") in edge_keys
    assert ("https://openalex.org/A1", "https://openalex.org/A3") not in edge_keys

    metrics = _read_csv(output_dir / "author_metrics.csv")
    assert {row["author_key"] for row in metrics if row["author"] == "Rui Zhang"} == {
        "https://openalex.org/A1",
        "https://openalex.org/A3",
    }
    assert "community_id" in metrics[0]

    diagnostics = _read_csv(output_dir / "author_network_diagnostics.csv")
    diagnostic_values = {row["metric"]: row["value"] for row in diagnostics}
    assert diagnostic_values["author_mentions_with_id"] == "4"
    assert diagnostic_values["unique_author_keys"] == "4"


def test_build_analysis_assets_can_select_source_filename_template(tmp_path):
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "analysis"
    pubmed_dir = raw_dir / "pubmed"
    pubmed_dir.mkdir(parents=True)
    pubmed_dir.joinpath("pubmed_3.jsonl").write_text(
        json.dumps(
            _wrapper("SMOKE", title="Smoke Paper", year=2020, authors=["Smoke Author"], keywords=["smoke"]),
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    pubmed_dir.joinpath("pubmed_500.jsonl").write_text(
        json.dumps(
            _wrapper("REAL", title="Real Paper", year=2024, authors=["Real Author"], keywords=["rag"]),
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_analysis_assets(
        raw_dir=raw_dir,
        output_dir=output_dir,
        sources=("pubmed",),
        filename_template="{source}_500.jsonl",
    )

    assert summary["input_records"] == 1
    assert summary["papers"] == 1
    assert summary["invalid_records"] == 0
    papers = json.loads(output_dir.joinpath("papers_clean.json").read_text(encoding="utf-8"))
    assert papers[0]["paper_id"] == "REAL"


def test_build_analysis_assets_skips_invalid_jsonl_lines(tmp_path):
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "analysis"
    pubmed_dir = raw_dir / "pubmed"
    pubmed_dir.mkdir(parents=True)
    pubmed_dir.joinpath("pubmed_500.jsonl").write_text(
        json.dumps(_wrapper("REAL", title="Real Paper", year=2024, authors=["Real Author"], keywords=["rag"]))
        + "\n"
        + '{"source": "pubmed", "raw": "truncated\n',
        encoding="utf-8",
    )

    summary = build_analysis_assets(
        raw_dir=raw_dir,
        output_dir=output_dir,
        sources=("pubmed",),
        filename_template="{source}_500.jsonl",
    )

    assert summary["input_records"] == 2
    assert summary["papers"] == 1
    assert summary["invalid_records"] == 1


def test_build_analysis_assets_keeps_future_year_suspects_without_formal_year(tmp_path):
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "analysis"
    pubmed_dir = raw_dir / "pubmed"
    pubmed_dir.mkdir(parents=True)
    record = {
        **_wrapper("FUTURE", title="Future Metadata Paper", year=2027, authors=["Future Author"], keywords=["metadata"]),
        "_sciscope_year_status": "future_year_suspect",
        "_sciscope_original_year": 2027,
    }
    pubmed_dir.joinpath("future_year_suspect.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = build_analysis_assets(raw_dir=raw_dir, output_dir=output_dir, sources=("pubmed",))

    assert summary["papers"] == 1
    papers = json.loads(output_dir.joinpath("papers_clean.json").read_text(encoding="utf-8"))
    assert papers[0]["paper_id"] == "FUTURE"
    assert papers[0]["year"] == ""
    assert papers[0]["original_year"] == 2027
    assert papers[0]["year_status"] == "future_year_suspect"
