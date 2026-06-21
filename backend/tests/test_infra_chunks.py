import json

from src.infra.chunks import build_chunk_assets, build_paper_chunks, paper_uid, split_text
from src.infra.postgres_loader import author_uid, keyword_uid, normalized_name


def test_build_paper_chunks_creates_abstract_full_text_and_keyword_chunks():
    paper = {
        "paper_id": "P1",
        "source": "pmc",
        "source_id": "PMC1",
        "title": "GraphRAG for Literature",
        "abstract": "Graph retrieval connects papers.",
        "full_text": "Full text evidence. " * 120,
        "keywords": ["RAG", "knowledge graph"],
        "year": 2024,
        "field": "computer science",
        "doi": "10.5555/demo",
        "url": "https://example.org/paper",
        "full_text_source": "arxiv_eprint",
        "full_text_url": "https://arxiv.org/e-print/2401.00001",
    }

    chunks = build_paper_chunks(paper, max_chars=200, overlap_chars=20)

    assert paper_uid(paper) == chunks[0]["paper_uid"]
    assert {chunk["chunk_type"] for chunk in chunks} == {"title_abstract", "full_text", "keywords"}
    assert all(chunk["token_estimate"] > 0 for chunk in chunks)
    assert all(chunk["chunk_uid"] for chunk in chunks)
    assert all(chunk["metadata"]["doi"] == "10.5555/demo" for chunk in chunks)
    assert all(chunk["metadata"]["text_source"] == "arxiv_eprint" for chunk in chunks)
    assert all(chunk["metadata"]["paper_chunk_count"] == len(chunks) for chunk in chunks)
    assert all(chunk["metadata"]["full_text_chunk_count"] >= 1 for chunk in chunks)


def test_split_text_uses_overlap_for_long_text():
    chunks = split_text("A" * 120 + ". " + "B" * 120, max_chars=100, overlap_chars=10)

    assert len(chunks) >= 2
    assert chunks[0]
    assert chunks[-1]


def test_build_chunk_assets_writes_jsonl_and_summary(tmp_path):
    input_path = tmp_path / "papers.json"
    output_path = tmp_path / "chunks.jsonl"
    summary_path = tmp_path / "summary.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "paper_id": "P1",
                    "source": "openalex",
                    "source_id": "W1",
                    "title": "RAG Paper",
                    "abstract": "Retrieval augmented generation.",
                    "keywords": ["rag"],
                    "year": 2024,
                    "field": "computer science",
                }
            ],
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_chunk_assets(input_path=input_path, output_path=output_path, summary_path=summary_path)
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

    assert summary["input_papers"] == 1
    assert summary["chunks"] == len(rows)
    assert summary["chunks_by_type"]["title_abstract"] == 1
    assert summary["papers_with_full_text_chunks"] == 0
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary


def test_postgres_loader_identifier_helpers_are_stable():
    assert normalized_name(" Ada   Chen ") == "ada chen"
    assert author_uid("Ada Chen") == author_uid("ada chen")
    assert keyword_uid("RAG") == keyword_uid("rag")
