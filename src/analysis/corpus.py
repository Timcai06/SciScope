from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RECENT_YEAR_START = 2022
RECENT_YEAR_END = 2026


TITLE_DEDUPE_MIN = 25  # min normalized-title length to dedupe by title alone

# Journal front-matter / non-paper records to drop entirely.
_FRONT_MATTER = {
    "editorial", "editorial board", "issue information", "contents",
    "table of contents", "correction", "corrigendum", "erratum", "masthead",
    "retraction", "retraction note", "cover image", "in this issue",
    "from the editor", "acknowledgements", "acknowledgments",
    "list of contributors", "reviewer acknowledgement", "author index",
    "subject index", "front matter", "back matter", "title page",
}


def _normalize_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _is_front_matter(title: str) -> bool:
    return title in _FRONT_MATTER


def _dedupe_key(paper: dict[str, Any]) -> str:
    source = str(paper.get("source") or "").strip()
    paper_id = str(paper.get("paper_id") or "").strip().lower()

    # Title-first for sufficiently long titles: collapses the same paper even
    # when copies differ by DOI presence (cross-source) or year (preprint vs
    # published). Long-title collisions are almost always true duplicates.
    title = _normalize_title(paper.get("title"))
    if len(title) >= TITLE_DEDUPE_MIN:
        return f"title:{title}"
    if paper_id.startswith("10."):
        return f"doi:{paper_id}"
    return f"source-id:{source}:{paper_id or title}"


def _record_score(paper: dict[str, Any]) -> tuple:
    """Completeness score; higher wins when a dedupe key repeats."""
    full_text = str(paper.get("full_text") or "")
    abstract = str(paper.get("abstract") or "")
    keywords = paper.get("keywords") or []
    authors = paper.get("authors") or []
    has_full_text = 100 if len(full_text) > 200 else 0
    return (
        has_full_text,
        min(len(abstract) // 100, 20),
        len(keywords),
        min(len(authors), 10),
        str(paper.get("crawled_at") or ""),  # tie-break: most recent crawl
    )


def _is_recent_year(value: Any, *, year_start: int, year_end: int) -> bool:
    return str(value or "").isdigit() and year_start <= int(value) <= year_end


def build_processed_corpus(
    *,
    input_path: str | Path = "data/analysis/papers_clean.json",
    output_path: str | Path = "data/processed/papers_corpus.json",
    summary_path: str | Path = "data/processed/papers_corpus.summary.json",
    year_start: int = RECENT_YEAR_START,
    year_end: int = RECENT_YEAR_END,
) -> dict[str, Any]:
    source = Path(input_path)
    output = Path(output_path)
    summary_output = Path(summary_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    papers = json.loads(source.read_text(encoding="utf-8")) if source.exists() else []
    best: dict[str, dict[str, Any]] = {}
    best_score: dict[str, tuple] = {}
    duplicates = 0
    front_matter_removed = 0
    for paper in papers:
        if _is_front_matter(_normalize_title(paper.get("title"))):
            front_matter_removed += 1
            continue
        key = _dedupe_key(paper)
        score = _record_score(paper)
        if key in best:
            duplicates += 1
            if score <= best_score[key]:
                continue  # keep the existing, more complete record
        best[key] = paper
        best_score[key] = score

    corpus = [
        {
            **paper,
            "is_recent_window": _is_recent_year(paper.get("year"), year_start=year_start, year_end=year_end),
        }
        for paper in best.values()
    ]

    summary = {
        "input_records": len(papers),
        "corpus_records": len(corpus),
        "duplicates": duplicates,
        "front_matter_removed": front_matter_removed,
        "recent_year_start": year_start,
        "recent_year_end": year_end,
        "recent_records": sum(1 for paper in corpus if paper["is_recent_window"]),
        "sources": sorted({paper.get("source") for paper in corpus if paper.get("source")}),
        "output": str(output),
    }
    output.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
