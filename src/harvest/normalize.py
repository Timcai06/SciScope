from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from data_pipeline.normalize import normalize_paper


def _restore_openalex_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: dict[int, str] = {}
    for word, offsets in index.items():
        for offset in offsets:
            positions[int(offset)] = word
    return " ".join(positions[i] for i in sorted(positions))


def _author_names(work: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = str(author.get("display_name") or "").strip()
        if name:
            names.append(name)
    return names


def _keywords(work: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for keyword in work.get("keywords") or []:
        display_name = str(keyword.get("display_name") or "").strip()
        if display_name:
            values.append(display_name)
    for concept in work.get("concepts") or []:
        display_name = str(concept.get("display_name") or "").strip()
        score = float(concept.get("score") or 0)
        if display_name and score >= 0.3:
            values.append(display_name)
    primary_topic = work.get("primary_topic") or {}
    topic_name = str(primary_topic.get("display_name") or "").strip()
    if topic_name:
        values.append(topic_name)
    return list(dict.fromkeys(values))[:12]


def _field(work: dict[str, Any], fallback: str) -> str:
    primary_topic = work.get("primary_topic") or {}
    for key in ("domain", "field"):
        value = primary_topic.get(key) or {}
        display_name = str(value.get("display_name") or "").strip()
        if display_name:
            return display_name
    return fallback or "unknown"


def _year_from_date(value: Any) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else ""
    return value


def _strip_markup(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def _full_text(work: dict[str, Any]) -> str:
    return str(work.get("body_excerpt") or work.get("fullText") or work.get("full_text") or "").strip()


def _crossref_year(work: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued"):
        parts = (work.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            return _year_from_date(parts[0][0])
    return None


def _crossref_authors(work: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for author in work.get("author") or []:
        name = " ".join(
            part for part in [str(author.get("given") or "").strip(), str(author.get("family") or "").strip()] if part
        )
        if name:
            authors.append(name)
    return authors


def openalex_work_to_paper(wrapper: dict[str, Any]) -> dict[str, Any]:
    work = wrapper.get("raw") or wrapper
    source_id = str(wrapper.get("source_id") or work.get("id") or "").rstrip("/")
    paper_id = source_id.rsplit("/", 1)[-1] if source_id else ""
    return normalize_paper(
        {
            "paper_id": paper_id,
            "title": work.get("display_name") or work.get("title") or "",
            "abstract": _restore_openalex_abstract(work.get("abstract_inverted_index")),
            "authors": _author_names(work),
            "year": work.get("publication_year"),
            "keywords": _keywords(work),
            "field": _field(work, str(wrapper.get("field_seed") or "unknown")),
            "full_text": _full_text(work),
        }
    )


def arxiv_work_to_paper(wrapper: dict[str, Any]) -> dict[str, Any]:
    work = wrapper.get("raw") or wrapper
    source_id = str(wrapper.get("source_id") or work.get("id") or "").strip()
    paper_id = source_id.rsplit("/", 1)[-1].removesuffix("v1").removesuffix("v2").removesuffix("v3")
    return normalize_paper(
        {
            "paper_id": paper_id,
            "title": work.get("title") or "",
            "abstract": work.get("summary") or "",
            "authors": work.get("authors") or [],
            "year": _year_from_date(work.get("published") or work.get("updated")),
            "keywords": work.get("categories") or [],
            "field": wrapper.get("field_seed") or "unknown",
            "full_text": _full_text(work),
        }
    )


def simple_raw_to_paper(wrapper: dict[str, Any]) -> dict[str, Any]:
    work = wrapper.get("raw") or wrapper
    source = str(wrapper.get("source") or "").strip()
    id_key = {"pubmed": "pmid", "pmc": "pmcid", "core": "id"}.get(source, "id")
    authors = work.get("authors") or []
    if authors and isinstance(authors[0], dict):
        authors = [str(item.get("name") or "").strip() for item in authors]
    return normalize_paper(
        {
            "paper_id": work.get(id_key) or wrapper.get("source_id") or "",
            "title": work.get("title") or "",
            "abstract": work.get("abstract") or "",
            "authors": authors,
            "year": work.get("year") or work.get("yearPublished") or _year_from_date(work.get("publishedDate")),
            "keywords": work.get("keywords") or work.get("topics") or [],
            "field": wrapper.get("field_seed") or "unknown",
            "full_text": _full_text(work),
        }
    )


def crossref_work_to_paper(wrapper: dict[str, Any]) -> dict[str, Any]:
    work = wrapper.get("raw") or wrapper
    return normalize_paper(
        {
            "paper_id": work.get("DOI") or wrapper.get("source_id") or "",
            "title": _first(work.get("title")) or "",
            "abstract": _strip_markup(work.get("abstract")),
            "authors": _crossref_authors(work),
            "year": _crossref_year(work),
            "keywords": work.get("subject") or [],
            "field": wrapper.get("field_seed") or "unknown",
            "full_text": _full_text(work),
        }
    )


def semantic_scholar_work_to_paper(wrapper: dict[str, Any]) -> dict[str, Any]:
    work = wrapper.get("raw") or wrapper
    keywords = list(work.get("fieldsOfStudy") or [])
    keywords.extend(str(item.get("category") or "").strip() for item in work.get("s2FieldsOfStudy") or [])
    return normalize_paper(
        {
            "paper_id": work.get("paperId") or wrapper.get("source_id") or "",
            "title": work.get("title") or "",
            "abstract": work.get("abstract") or "",
            "authors": [str(author.get("name") or "").strip() for author in work.get("authors") or []],
            "year": work.get("year"),
            "keywords": [keyword for keyword in keywords if keyword],
            "field": wrapper.get("field_seed") or "unknown",
            "full_text": _full_text(work),
        }
    )


def doaj_work_to_paper(wrapper: dict[str, Any]) -> dict[str, Any]:
    work = wrapper.get("raw") or wrapper
    bibjson = work.get("bibjson") or {}
    keywords = list(bibjson.get("keywords") or [])
    keywords.extend(str(item.get("term") or "").strip() for item in bibjson.get("subject") or [])
    return normalize_paper(
        {
            "paper_id": work.get("id") or wrapper.get("source_id") or "",
            "title": bibjson.get("title") or work.get("title") or "",
            "abstract": bibjson.get("abstract") or work.get("abstract") or "",
            "authors": [str(author.get("name") or "").strip() for author in bibjson.get("author") or []],
            "year": bibjson.get("year") or _year_from_date(bibjson.get("month")),
            "keywords": [keyword for keyword in keywords if keyword],
            "field": wrapper.get("field_seed") or "unknown",
            "full_text": _full_text(work),
        }
    )


def paper_wrapper_to_paper(wrapper: dict[str, Any]) -> dict[str, Any]:
    source = str(wrapper.get("source") or "openalex")
    if source == "openalex":
        return openalex_work_to_paper(wrapper)
    if source == "arxiv":
        return arxiv_work_to_paper(wrapper)
    if source in {"pubmed", "pmc", "core"}:
        return simple_raw_to_paper(wrapper)
    if source == "crossref":
        return crossref_work_to_paper(wrapper)
    if source == "semantic_scholar":
        return semantic_scholar_work_to_paper(wrapper)
    if source == "doaj":
        return doaj_work_to_paper(wrapper)
    raise ValueError(f"Unsupported source: {source}")


def normalize_raw_jsonl(input_path: str | Path, output_path: str | Path) -> dict[str, int]:
    source = Path(input_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    papers: list[dict[str, Any]] = []
    seen: set[str] = set()
    input_count = 0
    duplicate_count = 0
    invalid_count = 0
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            input_count += 1
            try:
                wrapper = json.loads(line)
                paper = paper_wrapper_to_paper(wrapper)
            except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                invalid_count += 1
                continue
            dedupe_key = paper["paper_id"] or f"{paper['title']}::{paper['year']}"
            if dedupe_key in seen:
                duplicate_count += 1
                continue
            seen.add(dedupe_key)
            papers.append(paper)

    output.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "input_records": input_count,
        "output_records": len(papers),
        "duplicates": duplicate_count,
        "invalid_records": invalid_count,
    }
