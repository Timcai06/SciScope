import json

from src.analysis.corpus import build_processed_corpus


def test_build_processed_corpus_dedupes_and_marks_recent_window(tmp_path):
    input_path = tmp_path / "papers_clean.json"
    output_path = tmp_path / "papers_corpus.json"
    summary_path = tmp_path / "papers_corpus.summary.json"
    input_path.write_text(
        json.dumps(
            [
                {"source": "openalex", "paper_id": "OA1", "title": "Shared Scientific Discovery Paper", "year": 2024},
                {"source": "crossref", "paper_id": "10.1234/demo", "title": "DOI Paper", "year": 2023},
                {"source": "doaj", "paper_id": "D1", "title": "Shared Scientific Discovery Paper", "year": 2024},
                {"source": "pmc", "paper_id": "PMC1", "title": "Historical Paper", "year": 2018},
            ],
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_processed_corpus(input_path=input_path, output_path=output_path, summary_path=summary_path)
    corpus = json.loads(output_path.read_text(encoding="utf-8"))

    assert summary["input_records"] == 4
    assert summary["corpus_records"] == 3
    assert summary["duplicates"] == 1
    assert summary["recent_records"] == 2
    assert [paper["is_recent_window"] for paper in corpus] == [True, True, False]
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary


def test_build_processed_corpus_drops_garbage_full_text(tmp_path):
    input_path = tmp_path / "papers_clean.json"
    output_path = tmp_path / "papers_corpus.json"
    summary_path = tmp_path / "papers_corpus.summary.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "source": "arxiv",
                    "paper_id": "2401.00001",
                    "title": "PDF Garbage",
                    "year": 2024,
                    "full_text": "4 0 obj << /Type /Page >> stream binary endstream endobj",
                },
                {
                    "source": "doaj",
                    "paper_id": "D1",
                    "title": "Bot Page",
                    "year": 2024,
                    "full_text": "<head><title>Radware Bot Manager Captcha</title><script></script>",
                },
                {
                    "source": "pmc",
                    "paper_id": "PMC1",
                    "title": "Good Full Text",
                    "year": 2024,
                    "full_text": "This is clean article text.",
                },
            ],
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    build_processed_corpus(input_path=input_path, output_path=output_path, summary_path=summary_path)
    corpus = json.loads(output_path.read_text(encoding="utf-8"))

    assert [paper["full_text"] for paper in corpus] == ["", "", "This is clean article text."]
