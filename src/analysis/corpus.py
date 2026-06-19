from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RECENT_YEAR_START = 2022
RECENT_YEAR_END = 2026


def _normalize_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _dedupe_key(paper: dict[str, Any]) -> str:
    source = str(paper.get("source") or "").strip()
    paper_id = str(paper.get("paper_id") or "").strip().lower()
    if paper_id.startswith("10."):
        return f"doi:{paper_id}"

    title = _normalize_title(paper.get("title"))
    year = paper.get("year") or ""
    if len(title) >= 20 and year:
        return f"title-year:{title}::{year}"
    return f"source-id:{source}:{paper_id or title}"


def _is_recent_year(value: Any, *, year_start: int, year_end: int) -> bool:
    return str(value or "").isdigit() and year_start <= int(value) <= year_end


def build_processed_corpus(
    *,
    input_path: str | Path = "data/analysis/papers_clean.json",
    output_path: str | Path = "data/processed/papers_corpus_50k.json",
    summary_path: str | Path = "data/processed/papers_corpus_50k.summary.json",
    year_start: int = RECENT_YEAR_START,
    year_end: int = RECENT_YEAR_END,
) -> dict[str, Any]:
    source = Path(input_path)
    output = Path(output_path)
    summary_output = Path(summary_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    papers = json.loads(source.read_text(encoding="utf-8")) if source.exists() else []
    corpus: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates = 0
    for paper in papers:
        key = _dedupe_key(paper)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        corpus.append(
            {
                **paper,
                "is_recent_window": _is_recent_year(paper.get("year"), year_start=year_start, year_end=year_end),
            }
        )

    summary = {
        "input_records": len(papers),
        "corpus_records": len(corpus),
        "duplicates": duplicates,
        "recent_year_start": year_start,
        "recent_year_end": year_end,
        "recent_records": sum(1 for paper in corpus if paper["is_recent_window"]),
        "sources": sorted({paper.get("source") for paper in corpus if paper.get("source")}),
        "output": str(output),
    }
    output.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
