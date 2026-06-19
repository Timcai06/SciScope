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
    assert {row["keyword"] for row in keywords} == {"rag", "ai", "knowledge graph"}

    keyword_year = _read_csv(output_dir / "keyword_year_matrix.csv")
    assert {"keyword": "rag", "year": "2024", "count": "1"} in keyword_year
    assert {"keyword": "rag", "year": "2025", "count": "1"} in keyword_year

    edges = _read_csv(output_dir / "author_collaboration_edges.csv")
    assert {"author_a": "Ada Chen", "author_b": "Lin Wang", "weight": "1"} in [
        {key: row[key] for key in ("author_a", "author_b", "weight")} for row in edges
    ]
    assert {"author_a": "Ada Chen", "author_b": "Bo Li", "weight": "1"} in [
        {key: row[key] for key in ("author_a", "author_b", "weight")} for row in edges
    ]

    quality = _read_csv(output_dir / "source_quality_report.csv")
    pubmed_quality = next(row for row in quality if row["source"] == "pubmed")
    assert pubmed_quality["records"] == "1"
    assert pubmed_quality["abstract_count"] == "1"

    saved_summary = json.loads(output_dir.joinpath("summary.json").read_text(encoding="utf-8"))
    assert saved_summary == summary


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
