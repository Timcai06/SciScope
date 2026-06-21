from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

from src.harvest.normalize import paper_wrapper_to_paper


DEFAULT_SOURCES = ("openalex", "arxiv", "pubmed", "pmc", "crossref", "doaj")
RECENT_YEAR_START = 2022
RECENT_YEAR_END = 2026
MAX_AUTHORS_FOR_CORE_NETWORK = 12
MAX_CORE_AUTHOR_GRAPH_EDGES = 25_000
TOPIC_SAMPLE_LIMIT = 50_000
KEYWORD_GRAPH_EDGE_LIMIT = 8_000
KEYWORD_EXTRACTION_SAMPLE_LIMIT = 50_000
KEYWORD_DRIFT_TOP_N = 40
INCREMENTAL_CACHE_VERSION = "2026-06-21-v2"

KEYWORD_ALIASES = {
    "ai": "artificial intelligence",
    "retrieval-augmented generation": "retrieval augmented generation",
    "retrieval augmented generation": "retrieval augmented generation",
    "rag": "retrieval augmented generation",
    "large language model": "large language model",
    "large language models": "large language model",
    "large-language model": "large language model",
    "large-language models": "large language model",
    "llm": "large language model",
    "llms": "large language model",
    "g n n": "graph neural network",
    "gnn": "graph neural network",
    "graph neural nets": "graph neural network",
    "graph neural networks": "graph neural network",
    "knowledge graphs": "knowledge graph",
    "machine-learning": "machine learning",
    "deep-learning": "deep learning",
    "vision-language model": "vision language model",
    "vision-language models": "vision language model",
    "vision language models": "vision language model",
    "vlm": "vision language model",
    "vlms": "vision language model",
    "nlp": "natural language processing",
    "natural language processing": "natural language processing",
    "natural language processing nlp": "natural language processing",
    "biomedical nlp": "biomedical nlp",
    "covid19": "covid 19",
    "covid-19": "covid 19",
}

TEXT_SIGNAL_TERMS = {
    "artificial intelligence": (
        r"\bartificial intelligence\b",
        r"\bai\b",
    ),
    "battery": (
        r"\bbatter(?:y|ies)\b",
        r"\blithium ion\b",
    ),
    "biomedical nlp": (
        r"\bbiomedical nlp\b",
        r"\bbiomedical natural language processing\b",
        r"\bclinical nlp\b",
    ),
    "cancer": (
        r"\bcancer\b",
        r"\btumo[u]?r\b",
        r"\boncology\b",
    ),
    "catalyst discovery": (
        r"\bcatalyst discovery\b",
        r"\bcatalytic discovery\b",
        r"\bcatalyst design\b",
    ),
    "clinical search": (
        r"\bclinical search\b",
        r"\bclinical retrieval\b",
    ),
    "computational biology": (
        r"\bcomputational biology\b",
        r"\bbioinformatics\b",
    ),
    "covid 19": (
        r"\bcovid\s*19\b",
        r"\bsars cov 2\b",
    ),
    "data science": (
        r"\bdata science\b",
    ),
    "deep learning": (
        r"\bdeep learning\b",
        r"\bdeep neural network(?:s)?\b",
    ),
    "diffusion model": (
        r"\bdiffusion model(?:s)?\b",
        r"\bdenoising diffusion\b",
    ),
    "drug discovery": (
        r"\bdrug discovery\b",
        r"\bdrug design\b",
        r"\bdrug repurposing\b",
    ),
    "graph neural network": (
        r"\bgraph neural network(?:s)?\b",
        r"\bgnn(?:s)?\b",
    ),
    "information retrieval": (
        r"\binformation retrieval\b",
        r"\bneural retrieval\b",
    ),
    "knowledge graph": (
        r"\bknowledge graph(?:s)?\b",
        r"\bknowledge graph embedding(?:s)?\b",
    ),
    "large language model": (
        r"\blarge language model(?:s)?\b",
        r"\bllm(?:s)?\b",
        r"\bfoundation model(?:s)?\b",
    ),
    "machine learning": (
        r"\bmachine learning\b",
    ),
    "materials informatics": (
        r"\bmaterials informatics\b",
        r"\bmaterial informatics\b",
        r"\bmaterials discovery\b",
    ),
    "multimodal learning": (
        r"\bmultimodal learning\b",
        r"\bmultimodal model(?:s)?\b",
        r"\bmultimodal large language model(?:s)?\b",
    ),
    "nanotechnology": (
        r"\bnanotechnology\b",
        r"\bnanomaterial(?:s)?\b",
    ),
    "natural language processing": (
        r"\bnatural language processing\b",
        r"\bnlp\b",
    ),
    "prompt engineering": (
        r"\bprompt engineering\b",
        r"\bprompt tuning\b",
        r"\binstruction tuning\b",
    ),
    "question answering": (
        r"\bquestion answering\b",
        r"\bqa system(?:s)?\b",
    ),
    "retrieval augmented generation": (
        r"\bretrieval augmented generation\b",
        r"\bretrieval augmentation\b",
        r"\bretrieval augmented\b",
        r"\brag\b",
    ),
    "transformer": (
        r"\btransformer(?:s)?\b",
        r"\btransformer based\b",
    ),
    "vision language model": (
        r"\bvision language model(?:s)?\b",
        r"\bvision language pretraining\b",
        r"\bvlm(?:s)?\b",
    ),
}
TEXT_SIGNAL_PATTERNS = {
    keyword: tuple(re.compile(pattern) for pattern in patterns)
    for keyword, patterns in TEXT_SIGNAL_TERMS.items()
}

GENERIC_KEYWORDS = {
    "article",
    "chemistry",
    "computer science",
    "health sciences",
    "humans",
    "life sciences",
    "materials science",
    "medicine",
    "method",
    "methods",
    "model",
    "models",
    "science",
    "scientific reports",
    "study",
}


def _iter_wrappers(
    raw_dir: Path,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    filename_template: str | None = None,
):
    for source in sources:
        source_dir = raw_dir / source
        if not source_dir.exists():
            continue
        paths = [source_dir / filename_template.format(source=source)] if filename_template else sorted(source_dir.glob("*.jsonl"))
        for path in paths:
            if not path.exists():
                continue
            if path.name.endswith(".tmp") or ".tmp" in path.suffixes:
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        yield None


def _dedupe_key(paper: dict[str, Any], wrapper: dict[str, Any]) -> str:
    paper_id = str(paper.get("paper_id") or "").strip()
    source = str(wrapper.get("source") or "").strip()
    if paper_id:
        return f"{source}:{paper_id}"
    return f"{paper.get('title') or ''}::{paper.get('year') or ''}".lower()


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _load_incremental_cache(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    checked_version = False
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not checked_version:
                checked_version = True
                if record.get("cache_version") != INCREMENTAL_CACHE_VERSION:
                    return {}
            if record.get("cache_version") != INCREMENTAL_CACHE_VERSION:
                continue
            cache_key = str(record.get("cache_key") or "")
            if cache_key:
                records[cache_key] = record
    return records


def _write_incremental_cache(path: Path, records: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _paper_with_source(wrapper: dict[str, Any]) -> dict[str, Any]:
    paper = paper_wrapper_to_paper(wrapper)
    raw_metadata = _raw_metadata(wrapper)
    year_status = str(wrapper.get("_sciscope_year_status") or "normal")
    if year_status == "future_year_suspect":
        paper = {
            **paper,
            "year": "",
            "original_year": wrapper.get("_sciscope_original_year"),
            "year_status": year_status,
        }
    return {
        **paper,
        "source": str(wrapper.get("source") or ""),
        "source_id": str(wrapper.get("source_id") or ""),
        "query": str(wrapper.get("query") or ""),
        "field_seed": str(wrapper.get("field_seed") or ""),
        "crawled_at": str(wrapper.get("crawled_at") or ""),
        "text_for_analysis": _text_for_analysis(paper),
        **raw_metadata,
    }


def _year_value(value: Any) -> int | None:
    if str(value or "").isdigit():
        return int(value)
    return None


def _is_recent_year(value: Any) -> bool:
    year = _year_value(value)
    return year is not None and RECENT_YEAR_START <= year <= RECENT_YEAR_END


def _normalize_keyword(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    text = text.replace("_", " ")
    text = re.sub(r"[-/]+", " ", text)
    text = re.sub(r"[^a-z0-9 +#]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 4 and text.endswith("ies"):
        text = f"{text[:-3]}y"
    elif len(text) > 4 and text.endswith("s") and not text.endswith("ss"):
        text = text[:-1]
    return KEYWORD_ALIASES.get(text, text)


def _is_keyword_signal(value: str) -> bool:
    keyword = _normalize_keyword(value)
    if len(keyword) < 3 or keyword in GENERIC_KEYWORDS:
        return False
    if re.fullmatch(r"[a-z]{1,5}\.[a-z0-9.-]{1,12}", keyword):
        return False
    if keyword.isdigit():
        return False
    return True


def _text_for_analysis(paper: dict[str, Any]) -> str:
    title = str(paper.get("title") or "").strip()
    abstract = str(paper.get("abstract") or "").strip()
    return re.sub(r"\s+", " ", f"{title} {title} {abstract}").strip()


def _extract_text_signal_terms(paper: dict[str, Any]) -> set[str]:
    text = str(paper.get("text_for_analysis") or "")
    if not text:
        text = _text_for_analysis(paper)
    normalized_text = _normalize_keyword(text)
    found: set[str] = set()
    for keyword, patterns in TEXT_SIGNAL_PATTERNS.items():
        if any(pattern.search(normalized_text) for pattern in patterns):
            found.add(keyword)
    return found


def _raw_metadata(wrapper: dict[str, Any]) -> dict[str, str]:
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    doi = str(raw.get("doi") or raw.get("DOI") or "").strip()
    url = str(raw.get("url") or raw.get("URL") or raw.get("id") or raw.get("source_id") or wrapper.get("source_id") or "").strip()
    return {
        "doi": doi,
        "url": url,
        "full_text_source": str(raw.get("full_text_source") or "").strip(),
        "full_text_url": str(raw.get("full_text_url") or "").strip(),
    }


def _clean_taxon(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text


def _first_taxon(values: list[Any]) -> str:
    for value in values:
        text = _clean_taxon(value)
        if text:
            return text
    return ""


def _arxiv_taxonomy(categories: list[str]) -> tuple[str, str, str]:
    primary = categories[0] if categories else ""
    prefix = primary.split(".", 1)[0].lower()
    domain = "Physical Sciences"
    field = "Physics"
    subfield = primary
    category_labels = {
        "cs.ai": ("Computer Science", "Artificial Intelligence", "Artificial Intelligence"),
        "cs.cl": ("Computer Science", "Artificial Intelligence", "Natural Language Processing"),
        "cs.cv": ("Computer Science", "Artificial Intelligence", "Computer Vision"),
        "cs.lg": ("Computer Science", "Artificial Intelligence", "Machine Learning"),
        "cs.ir": ("Computer Science", "Information Systems", "Information Retrieval"),
        "cs.cr": ("Computer Science", "Security", "Computer Security"),
        "cs.ro": ("Computer Science", "Robotics", "Robotics"),
        "cond-mat.mtrl-sci": ("Physical Sciences", "Materials Science", "Materials Science"),
        "q-bio.qm": ("Life Sciences", "Computational Biology", "Quantitative Methods"),
        "q-bio.gn": ("Life Sciences", "Computational Biology", "Genomics"),
        "q-bio.nc": ("Life Sciences", "Computational Biology", "Neurons and Cognition"),
        "stat.ml": ("Computer Science", "Statistics", "Statistical Machine Learning"),
        "stat.me": ("Physical Sciences", "Statistics", "Statistical Methods"),
        "eess.iv": ("Computer Science", "Electrical Engineering", "Image and Video Processing"),
    }
    if primary.lower() in category_labels:
        return category_labels[primary.lower()]
    if prefix == "cs":
        domain, field = "Computer Science", "Computer Science"
    elif prefix == "q-bio":
        domain, field = "Life Sciences", "Computational Biology"
    elif prefix in {"cond-mat"}:
        domain, field = "Physical Sciences", "Materials Science"
    elif prefix in {"stat"}:
        domain, field = "Physical Sciences", "Statistics"
    elif prefix in {"eess"}:
        domain, field = "Computer Science", "Electrical Engineering"
    elif prefix in {"math"}:
        domain, field = "Physical Sciences", "Mathematics"
    elif prefix in {"astro-ph", "gr-qc", "hep-ex", "hep-lat", "hep-ph", "hep-th", "nucl-ex", "nucl-th"}:
        domain, field = "Physical Sciences", "Physics"
    return domain, field, subfield


def _subject_taxonomy(subjects: list[str], fallback: str) -> tuple[str, str, str]:
    joined = " ".join(subjects).lower()
    fallback_clean = _clean_taxon(fallback)
    if any(token in joined for token in ("computer", "information technology", "electronic")):
        return "Computer Science", "Computer Science", _first_taxon(subjects)
    if any(token in joined for token in ("medicine", "medical", "public health", "health")):
        return "Health Sciences", "Medicine", _first_taxon(subjects)
    if any(token in joined for token in ("biology", "biological", "genetics", "life sciences")):
        return "Life Sciences", "Biology", _first_taxon(subjects)
    if any(token in joined for token in ("material", "nanomaterial", "chemical technology", "engineering")):
        return "Physical Sciences", "Materials Science", _first_taxon(subjects)
    if any(token in joined for token in ("physics", "chemistry", "mathematics", "science")):
        return "Physical Sciences", "Physical Sciences", _first_taxon(subjects)
    if any(token in joined for token in ("social", "education", "economics", "law", "political")):
        return "Social Sciences", "Social Sciences", _first_taxon(subjects)
    if fallback_clean:
        return _subject_taxonomy([fallback_clean], "")
    return "Cross-field", "Unknown", ""


def _keyword_subfield(keywords: list[Any]) -> str:
    generic = {"article", "humans", "male", "female", "adult", "study", "method", "methods"}
    for keyword in keywords:
        text = _normalize_keyword(keyword)
        if len(text) >= 4 and text not in generic:
            return text
    return ""


def _taxonomy_for_paper(wrapper: dict[str, Any], paper: dict[str, Any]) -> dict[str, Any]:
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    source = str(wrapper.get("source") or paper.get("source") or "")
    domain = ""
    field = ""
    subfield = ""
    taxonomy_source = "field_seed"
    confidence = 0.55
    raw_terms: list[str] = []

    if source == "openalex":
        primary_topic = raw.get("primary_topic") if isinstance(raw.get("primary_topic"), dict) else {}
        domain = _clean_taxon((primary_topic.get("domain") or {}).get("display_name") if isinstance(primary_topic.get("domain"), dict) else "")
        field = _clean_taxon((primary_topic.get("field") or {}).get("display_name") if isinstance(primary_topic.get("field"), dict) else "")
        subfield = _clean_taxon((primary_topic.get("subfield") or {}).get("display_name") if isinstance(primary_topic.get("subfield"), dict) else "")
        topic_name = _clean_taxon(primary_topic.get("display_name"))
        raw_terms = [term for term in (topic_name, domain, field, subfield) if term]
        taxonomy_source = "openalex_primary_topic"
        confidence = 0.95 if raw_terms else 0.55
    elif source == "arxiv":
        categories = raw.get("categories") or raw.get("category") or []
        if isinstance(categories, str):
            categories = categories.split()
        categories = [_clean_taxon(category) for category in categories if _clean_taxon(category)]
        domain, field, subfield = _arxiv_taxonomy(categories)
        raw_terms = categories
        taxonomy_source = "arxiv_category"
        confidence = 0.9 if categories else 0.55
    elif source == "doaj":
        bibjson = raw.get("bibjson") if isinstance(raw.get("bibjson"), dict) else {}
        subjects = []
        for subject in bibjson.get("subject") or []:
            if isinstance(subject, dict):
                subjects.append(_clean_taxon(subject.get("term") or subject.get("code")))
            else:
                subjects.append(_clean_taxon(subject))
        subjects = [subject for subject in subjects if subject]
        domain, field, subfield = _subject_taxonomy(subjects, str(wrapper.get("field_seed") or ""))
        raw_terms = subjects
        taxonomy_source = "doaj_subject"
        confidence = 0.82 if subjects else 0.55
    elif source in {"pubmed", "pmc"}:
        keywords = list(raw.get("keywords") or raw.get("mesh_terms") or paper.get("keywords") or [])
        domain, field = _subject_taxonomy([str(wrapper.get("field_seed") or paper.get("field") or "")], "")[:2]
        if domain == "Cross-field":
            domain, field = "Health Sciences", "Medicine"
        subfield = _keyword_subfield(keywords)
        raw_terms = [_clean_taxon(keyword) for keyword in keywords[:8] if _clean_taxon(keyword)]
        taxonomy_source = "biomedical_keywords"
        confidence = 0.75 if raw_terms else 0.6
    else:
        domain, field, subfield = _subject_taxonomy([str(wrapper.get("field_seed") or paper.get("field") or "")], "")
        raw_terms = [term for term in (str(wrapper.get("field_seed") or ""), str(paper.get("field") or "")) if term]

    if not domain or not field:
        domain, field, fallback_subfield = _subject_taxonomy([str(wrapper.get("field_seed") or paper.get("field") or "")], "")
        subfield = subfield or fallback_subfield
    if not subfield:
        subfield = _keyword_subfield(list(paper.get("keywords") or []))

    return {
        "paper_id": paper.get("paper_id") or "",
        "source": source,
        "year": paper.get("year") or "",
        "domain": domain or "Cross-field",
        "field": field or "Unknown",
        "subfield": subfield or "",
        "taxonomy_source": taxonomy_source,
        "taxonomy_confidence": round(confidence, 2),
        "raw_taxonomy_terms": ";".join(raw_terms[:12]),
        "has_full_text": int(bool(paper.get("full_text"))),
    }


def _build_taxonomy_coverage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("source") or ""),
            str(row.get("domain") or ""),
            str(row.get("field") or ""),
            str(row.get("subfield") or ""),
        )
        current = grouped.setdefault(
            key,
            {
                "source": key[0],
                "domain": key[1],
                "field": key[2],
                "subfield": key[3],
                "records": 0,
                "full_text_count": 0,
            },
        )
        current["records"] += 1
        current["full_text_count"] += int(row.get("has_full_text") or 0)
    output = []
    for row in grouped.values():
        records = int(row["records"])
        full_text_count = int(row["full_text_count"])
        output.append(
            {
                **row,
                "full_text_rate": round(full_text_count / records, 4) if records else 0,
            }
        )
    return sorted(output, key=lambda row: (-int(row["records"]), row["source"], row["domain"], row["field"], row["subfield"]))


def _raw_paths(raw_path: Path, sources: tuple[str, ...], filename_template: str | None) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []
    for source in sources:
        source_dir = raw_path / source
        if not source_dir.exists():
            continue
        candidates = [source_dir / filename_template.format(source=source)] if filename_template else sorted(source_dir.glob("*.jsonl"))
        for path in candidates:
            if path.exists() and not path.name.endswith(".tmp") and ".tmp" not in path.suffixes:
                paths.append((source, path))
    return paths


def _build_collection_manifest(raw_path: Path, sources: tuple[str, ...], filename_template: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    year_pattern = re.compile(r"(19|20)\d{2}")
    for source, path in _raw_paths(raw_path, sources, filename_template):
        records = 0
        invalid_json = 0
        years: Counter[str] = Counter()
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                records += 1
                try:
                    wrapper = json.loads(line)
                except json.JSONDecodeError:
                    invalid_json += 1
                    continue
                status = str(wrapper.get("_sciscope_year_status") or "")
                year = wrapper.get("_sciscope_original_year") if status == "future_year_suspect" else None
                if year is None:
                    year = wrapper.get("_sciscope_canonical_year")
                if year is None:
                    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
                    year = raw.get("year") or raw.get("publication_year") or raw.get("publishedDate") or raw.get("published")
                match = year_pattern.search(str(year or ""))
                years[match.group(0) if match else "unknown_year"] += 1
        file_year = path.stem if path.stem.isdigit() else ""
        abnormal_years = sorted(year for year in years if year.isdigit() and int(year) > RECENT_YEAR_END)
        rows.append(
            {
                "source": source,
                "year_partition": file_year or path.stem,
                "file": str(path),
                "records": records,
                "file_size_bytes": path.stat().st_size,
                "empty_file": records == 0,
                "invalid_json_lines": invalid_json,
                "observed_years": ";".join(f"{year}:{count}" for year, count in sorted(years.items())),
                "abnormal_years": ";".join(abnormal_years),
            }
        )
    summary = {
        "collection_files": len(rows),
        "collection_records": sum(int(row["records"]) for row in rows),
        "empty_files": sum(1 for row in rows if row["empty_file"]),
        "invalid_json_lines": sum(int(row["invalid_json_lines"]) for row in rows),
        "abnormal_year_files": sum(1 for row in rows if row["abnormal_years"]),
    }
    return rows, summary


def _doc_key(paper: dict[str, Any]) -> str:
    return str(paper.get("paper_id") or paper.get("title") or id(paper))


def _build_keyword_assets(
    papers: list[dict[str, Any]],
    *,
    edge_cache_dir: Path | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    paper_keywords: list[dict[str, Any]] = []
    paper_keyword_signals: list[dict[str, Any]] = []
    alias_rows: dict[str, str] = {}
    keyword_year_docs: dict[tuple[str, int], dict[str, set[str]]] = defaultdict(lambda: {"explicit": set(), "text": set(), "fused": set()})
    keyword_representatives: dict[str, dict[str, Any]] = {}
    paper_keyword_docs: dict[str, dict[str, Any]] = {}
    docs_by_year = Counter(int(paper["year"]) for paper in papers if _is_recent_year(paper.get("year")))
    analyzable_docs_by_year = Counter(
        int(paper["year"])
        for paper in papers
        if _is_recent_year(paper.get("year")) and bool(str(paper.get("text_for_analysis") or "").strip())
    )

    for paper in papers:
        year = _year_value(paper.get("year"))
        paper_id = _doc_key(paper)
        seen_explicit_keywords: set[str] = set()
        paper_id_text = str(paper.get("paper_id") or "")
        source = str(paper.get("source") or "")
        paper_year = paper.get("year") or ""
        keyword_doc = paper_keyword_docs.setdefault(
            paper_id,
            {
                "doc_key": paper_id,
                "paper_id": paper_id_text,
                "source": source,
                "year": year,
                "paper_year": paper_year,
                "keywords": set(),
            },
        )
        for raw_keyword in paper.get("keywords") or []:
            keyword = _normalize_keyword(raw_keyword)
            if not keyword or not _is_keyword_signal(keyword) or keyword in seen_explicit_keywords:
                continue
            seen_explicit_keywords.add(keyword)
            keyword_doc["keywords"].add(keyword)
            alias_rows[str(raw_keyword).strip().lower()] = keyword
            row = {"paper_id": paper_id_text, "source": source, "year": paper_year, "keyword": keyword}
            paper_keywords.append(row)
            if year is not None:
                docs = keyword_year_docs[(keyword, year)]
                docs["explicit"].add(paper_id)
                docs["fused"].add(paper_id)
            paper_keyword_signals.append({**row, "signal_source": "explicit_keyword"})
            if keyword not in keyword_representatives or _is_recent_year(paper.get("year")):
                keyword_representatives[keyword] = paper

        seen_text_terms = set()
        for keyword in sorted(_extract_text_signal_terms(paper)):
            if not keyword or not _is_keyword_signal(keyword) or keyword in seen_text_terms:
                continue
            seen_text_terms.add(keyword)
            keyword_doc["keywords"].add(keyword)
            row = {"paper_id": paper_id_text, "source": source, "year": paper_year, "keyword": keyword}
            if year is not None:
                docs = keyword_year_docs[(keyword, year)]
                docs["text"].add(paper_id)
                docs["fused"].add(paper_id)
            paper_keyword_signals.append({**row, "signal_source": "title_abstract"})
            if keyword not in keyword_representatives or _is_recent_year(paper.get("year")):
                keyword_representatives[keyword] = paper

    keyword_year_rows: list[dict[str, Any]] = []
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))
    for (keyword, year), docs_by_signal in sorted(keyword_year_docs.items(), key=lambda item: (item[0][0], item[0][1])):
        total_docs = docs_by_year.get(year, 0)
        analyzable_docs = analyzable_docs_by_year.get(year, total_docs)
        explicit_count = len(docs_by_signal["explicit"])
        text_signal_count = len(docs_by_signal["text"])
        count = len(docs_by_signal["fused"])
        keyword_year_rows.append(
            {
                "keyword": keyword,
                "year": year,
                "count": count,
                "explicit_count": explicit_count,
                "text_signal_count": text_signal_count,
                "total_docs_in_year": total_docs,
                "analyzable_docs_in_year": analyzable_docs,
                "normalized_df": round(count / analyzable_docs, 6) if analyzable_docs else 0,
            }
        )

    grouped_counts: dict[str, dict[int, int]] = defaultdict(dict)
    grouped_explicit_counts: dict[str, dict[int, int]] = defaultdict(dict)
    grouped_text_counts: dict[str, dict[int, int]] = defaultdict(dict)
    grouped_norms: dict[str, dict[int, float]] = defaultdict(dict)
    for row in keyword_year_rows:
        keyword = str(row["keyword"])
        year = int(row["year"])
        grouped_counts[keyword][year] = int(row["count"])
        grouped_explicit_counts[keyword][year] = int(row["explicit_count"])
        grouped_text_counts[keyword][year] = int(row["text_signal_count"])
        grouped_norms[keyword][year] = float(row["normalized_df"])

    trend_rows: list[dict[str, Any]] = []
    for keyword, year_counts in grouped_counts.items():
        recent_values = [grouped_norms[keyword].get(year, 0.0) for year in years]
        baseline = sum(recent_values[:2]) / 2
        current = grouped_norms[keyword].get(RECENT_YEAR_END - 1, 0.0)
        ytd_value = grouped_norms[keyword].get(RECENT_YEAR_END, 0.0)
        doc_count = sum(year_counts.get(year, 0) for year in years)
        explicit_doc_count = sum(grouped_explicit_counts[keyword].get(year, 0) for year in years)
        text_signal_doc_count = sum(grouped_text_counts[keyword].get(year, 0) for year in years)
        if doc_count <= 0:
            continue
        growth_rate = (current - baseline) / baseline if baseline else (current if current else 0)
        burst_score = max(recent_values) / (sum(recent_values) / len(recent_values)) if sum(recent_values) else 0
        momentum = math.log1p(doc_count) * (growth_rate + current)
        representative = keyword_representatives.get(keyword, {})
        row = {
            "keyword": keyword,
            "doc_count": doc_count,
            "explicit_doc_count": explicit_doc_count,
            "text_signal_doc_count": text_signal_doc_count,
            "normalized_df": round(sum(recent_values) / len(recent_values), 6),
            "growth_rate": round(growth_rate, 6),
            "momentum_score": round(momentum, 6),
            "burst_score": round(burst_score, 6),
            "ytd_2026_normalized_df": round(ytd_value, 6),
            "representative_paper_id": representative.get("paper_id") or "",
            "representative_title": representative.get("title") or "",
            "representative_year": representative.get("year") or "",
        }
        for year in years:
            row[f"doc_count_{year}"] = year_counts.get(year, 0)
            row[f"explicit_count_{year}"] = grouped_explicit_counts[keyword].get(year, 0)
            row[f"text_signal_count_{year}"] = grouped_text_counts[keyword].get(year, 0)
            row[f"normalized_df_{year}"] = round(grouped_norms[keyword].get(year, 0.0), 6)
        trend_rows.append(row)
    trend_rows.sort(key=lambda row: (float(row["momentum_score"]), int(row["doc_count"])), reverse=True)
    alias_output = [{"raw_keyword": raw, "canonical_keyword": canonical} for raw, canonical in sorted(alias_rows.items()) if raw != canonical]
    keyword_docs = list(paper_keyword_docs.values())
    (
        keyword_edge_rows,
        keyword_metrics_rows,
        keyword_community_rows,
        keyword_burst_rows,
        keyword_lifecycle_rows,
        keyword_drift_rows,
        keyword_edge_cache_stats,
    ) = _build_keyword_network_assets(keyword_docs, keyword_year_rows, trend_rows, edge_cache_dir=edge_cache_dir)
    keyword_tfidf_rows, keyword_extraction_diagnostics = _build_keyword_extraction_assets(papers, keyword_drift_rows)
    return (
        paper_keywords,
        paper_keyword_signals,
        keyword_year_rows,
        trend_rows,
        alias_output,
        keyword_edge_rows,
        keyword_metrics_rows,
        keyword_community_rows,
        keyword_burst_rows,
        keyword_lifecycle_rows,
        keyword_drift_rows,
        keyword_tfidf_rows,
        keyword_extraction_diagnostics + keyword_edge_cache_stats,
    )


def _keyword_edge_signature(keyword_doc: dict[str, Any]) -> str:
    return _stable_hash(
        {
            "paper_id": keyword_doc.get("paper_id") or "",
            "doc_key": keyword_doc.get("doc_key") or keyword_doc.get("paper_id") or "",
            "source": keyword_doc.get("source") or "",
            "year": keyword_doc.get("paper_year") or keyword_doc.get("year") or "",
            "keywords": sorted(str(keyword) for keyword in keyword_doc.get("keywords", set())),
        }
    )


def _keyword_edge_contributions(keyword_doc: dict[str, Any]) -> list[dict[str, Any]]:
    keywords = sorted(str(keyword) for keyword in keyword_doc.get("keywords", set()) if str(keyword).strip())
    if len(keywords) < 2:
        return []
    weight = 2 / (len(keywords) * (len(keywords) - 1))
    year = keyword_doc.get("year")
    contributions: list[dict[str, Any]] = []
    for keyword_a, keyword_b in combinations(keywords, 2):
        contributions.append(
            {
                "keyword_a": keyword_a,
                "keyword_b": keyword_b,
                "paper_count": 1,
                "weight": weight,
                "year": year,
            }
        )
    return contributions


def _merge_keyword_edge_contribution(
    edge_stats: dict[tuple[str, str], dict[str, Any]],
    contribution: dict[str, Any],
) -> None:
    key = tuple(sorted((str(contribution["keyword_a"]), str(contribution["keyword_b"]))))
    year = _year_value(contribution.get("year"))
    stats = edge_stats.setdefault(
        key,
        {
            "keyword_a": key[0],
            "keyword_b": key[1],
            "paper_count": 0,
            "weight": 0.0,
            "first_year": year,
            "last_year": year,
            "years": set(),
            "active_years": 0,
        },
    )
    stats["paper_count"] += int(contribution.get("paper_count") or 1)
    stats["weight"] += float(contribution.get("weight") or 0)
    if year is not None:
        stats["years"].add(year)
        stats["first_year"] = min([item for item in (stats["first_year"], year) if item is not None])
        stats["last_year"] = max([item for item in (stats["last_year"], year) if item is not None])


def _load_keyword_edge_aggregate(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    edge_stats: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.exists():
        return edge_stats
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            keyword_a = str(row.get("keyword_a") or "").strip()
            keyword_b = str(row.get("keyword_b") or "").strip()
            if not keyword_a or not keyword_b or keyword_a == keyword_b:
                continue
            key = tuple(sorted((keyword_a, keyword_b)))
            edge_stats[key] = {
                "keyword_a": key[0],
                "keyword_b": key[1],
                "weight": float(row.get("weight") or 0),
                "paper_count": int(float(row.get("paper_count") or 0)),
                "first_year": _year_value(row.get("first_year")),
                "last_year": _year_value(row.get("last_year")),
                "years": set(),
                "active_years": int(float(row.get("active_years") or 0)),
            }
    return edge_stats


def _keyword_year_lookup(keyword_year_rows: list[dict[str, Any]]) -> tuple[dict[str, dict[int, int]], dict[str, dict[int, float]]]:
    counts: dict[str, dict[int, int]] = defaultdict(dict)
    normalized: dict[str, dict[int, float]] = defaultdict(dict)
    for row in keyword_year_rows:
        keyword = str(row["keyword"])
        year = int(row["year"])
        counts[keyword][year] = int(row.get("count") or 0)
        normalized[keyword][year] = float(row.get("normalized_df") or 0)
    return counts, normalized


def _keyword_lifecycle_stage(counts: dict[int, int], growth_rate: float) -> str:
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))
    values = [int(counts.get(year, 0)) for year in years]
    nonzero_years = [year for year in years if counts.get(year, 0) > 0]
    if not nonzero_years:
        return "decline"
    first_year = nonzero_years[0]
    peak_index = max(range(len(values)), key=lambda index: values[index])
    peak_year = years[peak_index]
    if first_year >= RECENT_YEAR_END - 1:
        return "emergence"
    if growth_rate >= 0.3 or (first_year > RECENT_YEAR_START and peak_year >= RECENT_YEAR_END - 1):
        return "growth"
    if peak_year < RECENT_YEAR_END - 1 and values[-1] < values[peak_index]:
        return "decline"
    return "maturity"


def _build_keyword_burst_and_lifecycle(
    keyword_year_rows: list[dict[str, Any]],
    trend_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    counts_by_keyword, normalized_by_keyword = _keyword_year_lookup(keyword_year_rows)
    trend_by_keyword = {str(row["keyword"]): row for row in trend_rows}
    years = list(range(RECENT_YEAR_START, RECENT_YEAR_END + 1))

    burst_rows: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []
    stage_by_keyword: dict[str, str] = {}
    for keyword, counts in sorted(counts_by_keyword.items()):
        trend = trend_by_keyword.get(keyword, {})
        doc_count = sum(int(counts.get(year, 0)) for year in years)
        if doc_count <= 0:
            continue
        peak_year = max(years, key=lambda year: int(counts.get(year, 0)))
        peak_count = int(counts.get(peak_year, 0))
        first_year = min(year for year in years if int(counts.get(year, 0)) > 0)
        last_year = max(year for year in years if int(counts.get(year, 0)) > 0)
        growth_rate = float(trend.get("growth_rate") or 0)
        stage = _keyword_lifecycle_stage(counts, growth_rate)
        stage_by_keyword[keyword] = stage
        lifecycle_rows.append(
            {
                "keyword": keyword,
                "lifecycle_stage": stage,
                "doc_count": doc_count,
                "first_year": first_year,
                "peak_year": peak_year,
                "last_year": last_year,
                "peak_count": peak_count,
                "growth_rate": round(growth_rate, 6),
                "burst_score": round(float(trend.get("burst_score") or 0), 6),
            }
        )
        for year in years:
            count = int(counts.get(year, 0))
            previous_year = year - 1
            previous_count = int(counts.get(previous_year, 0)) if previous_year in years else 0
            current_norm = float(normalized_by_keyword[keyword].get(year, 0))
            previous_norm = float(normalized_by_keyword[keyword].get(previous_year, 0)) if previous_year in years else 0.0
            if count <= 0 and previous_count <= 0:
                continue
            if previous_count == 0:
                annual_growth = float(count) if count else 0.0
            else:
                annual_growth = (count - previous_count) / max(previous_count, 1)
            burst_state = ""
            if count > 0 and previous_count == 0:
                burst_state = "emergence"
            elif annual_growth >= 0.3:
                burst_state = "growth"
            elif annual_growth <= -0.3:
                burst_state = "decline"
            if not burst_state:
                continue
            burst_score = math.log1p(count + previous_count) * abs(annual_growth)
            burst_rows.append(
                {
                    "keyword": keyword,
                    "year": year,
                    "previous_year": previous_year if previous_year in years else "",
                    "count": count,
                    "previous_count": previous_count,
                    "normalized_df": round(current_norm, 6),
                    "previous_normalized_df": round(previous_norm, 6),
                    "growth_rate": round(annual_growth, 6),
                    "burst_score": round(burst_score, 6),
                    "burst_state": burst_state,
                }
            )
    lifecycle_rows.sort(key=lambda row: (-int(row["doc_count"]), row["keyword"]))
    burst_rows.sort(key=lambda row: (-float(row["burst_score"]), row["keyword"], row["year"]))
    return burst_rows, lifecycle_rows, stage_by_keyword


def _counter_cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left).intersection(right)
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _build_keyword_context_drift(
    keyword_docs: list[dict[str, Any]],
    trend_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    top_keywords = {
        str(row["keyword"])
        for row in sorted(trend_rows, key=lambda item: (int(item.get("doc_count") or 0), float(item.get("momentum_score") or 0)), reverse=True)[
            :KEYWORD_DRIFT_TOP_N
        ]
    }
    contexts: dict[tuple[str, int], Counter[str]] = defaultdict(Counter)
    for keyword_doc in keyword_docs:
        year = _year_value(keyword_doc.get("year"))
        if year is None:
            continue
        keywords = sorted(str(keyword) for keyword in keyword_doc.get("keywords", set()) if str(keyword).strip())
        for keyword in keywords:
            if keyword not in top_keywords:
                continue
            contexts[(keyword, year)].update(other for other in keywords if other != keyword)

    rows: list[dict[str, Any]] = []
    for keyword in sorted(top_keywords):
        for year in range(RECENT_YEAR_START, RECENT_YEAR_END):
            left = contexts.get((keyword, year), Counter())
            right = contexts.get((keyword, year + 1), Counter())
            if not left or not right:
                continue
            similarity = _counter_cosine(left, right)
            rows.append(
                {
                    "keyword": keyword,
                    "year_from": year,
                    "year_to": year + 1,
                    "cosine_similarity": round(similarity, 6),
                    "drift_score": round(1 - similarity, 6),
                    "method": "keyword_context_cosine_proxy",
                    "significant": 0,
                }
            )
    if rows:
        scores = sorted(float(row["drift_score"]) for row in rows)
        threshold = scores[max(0, int(len(scores) * 0.9) - 1)]
        for row in rows:
            row["significant"] = int(float(row["drift_score"]) >= threshold)
    return sorted(rows, key=lambda row: (-float(row["drift_score"]), row["keyword"], row["year_from"]))


def _build_keyword_network_assets(
    keyword_docs: list[dict[str, Any]],
    keyword_year_rows: list[dict[str, Any]],
    trend_rows: list[dict[str, Any]],
    *,
    edge_cache_dir: Path | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    try:
        import networkx as nx
    except ImportError:
        nx = None

    edge_cache_path = edge_cache_dir / "keyword_edge_papers.jsonl" if edge_cache_dir else None
    previous_edge_path = edge_cache_dir.parent / "keyword_cooccurrence_edges.csv" if edge_cache_dir else None
    edge_cache = _load_incremental_cache(edge_cache_path) if edge_cache_path else {}
    cache_hits = 0
    cache_misses = 0
    cache_changed = False
    current_cache_keys: set[str] = set()
    keyword_doc_records: list[dict[str, Any]] = []

    for keyword_doc in keyword_docs:
        keywords = keyword_doc.get("keywords", set())
        if len(keywords) < 2:
            continue
        signature = _keyword_edge_signature(keyword_doc)
        cache_key = f"{keyword_doc.get('source') or ''}:{keyword_doc.get('doc_key') or keyword_doc.get('paper_id') or signature}"
        current_cache_keys.add(cache_key)
        cached = edge_cache.get(cache_key)
        cache_hit = bool(cached and cached.get("signature") == signature)
        if cached and not cache_hit:
            cache_changed = True
        keyword_doc_records.append({"cache_key": cache_key, "signature": signature, "keyword_doc": keyword_doc, "cache_hit": cache_hit})

    cache_removed = bool(set(edge_cache) - current_cache_keys)
    can_reuse_previous_edges = bool(edge_cache) and bool(previous_edge_path and previous_edge_path.exists()) and not cache_changed and not cache_removed
    edge_stats = _load_keyword_edge_aggregate(previous_edge_path) if can_reuse_previous_edges and previous_edge_path else {}

    for record in keyword_doc_records:
        if can_reuse_previous_edges and record["cache_hit"]:
            cache_hits += 1
            continue
        contributions = _keyword_edge_contributions(record["keyword_doc"])
        cache_misses += 1
        for contribution in contributions:
            _merge_keyword_edge_contribution(edge_stats, contribution)

    if edge_cache_path:
        _write_incremental_cache(
            edge_cache_path,
            (
                {
                    "cache_version": INCREMENTAL_CACHE_VERSION,
                    "cache_key": record["cache_key"],
                    "paper_id": record["keyword_doc"].get("paper_id") or "",
                    "source": record["keyword_doc"].get("source") or "",
                    "signature": record["signature"],
                }
                for record in keyword_doc_records
            ),
        )

    edge_rows = [
        {
            "keyword_a": stats["keyword_a"],
            "keyword_b": stats["keyword_b"],
            "weight": round(float(stats["weight"]), 6),
            "paper_count": int(stats["paper_count"]),
            "first_year": stats["first_year"] or "",
            "last_year": stats["last_year"] or "",
            "active_years": max(len(stats["years"]), int(stats.get("active_years") or 0)),
        }
        for stats in edge_stats.values()
    ]
    edge_rows.sort(key=lambda row: (-float(row["weight"]), -int(row["paper_count"]), row["keyword_a"], row["keyword_b"]))

    burst_rows, lifecycle_rows, stage_by_keyword = _build_keyword_burst_and_lifecycle(keyword_year_rows, trend_rows)
    drift_rows = _build_keyword_context_drift(keyword_docs, trend_rows)
    trend_by_keyword = {str(row["keyword"]): row for row in trend_rows}

    graph = nx.Graph() if nx is not None else None
    if graph is not None:
        for row in edge_rows[:KEYWORD_GRAPH_EDGE_LIMIT]:
            weight = float(row["weight"])
            graph.add_edge(row["keyword_a"], row["keyword_b"], weight=weight, distance=1 / weight if weight else 1)

    degree = dict(graph.degree(weight="weight")) if graph is not None and graph.number_of_nodes() else {}
    pagerank = nx.pagerank(graph, weight="weight") if nx is not None and graph is not None and graph.number_of_nodes() > 1 else {}
    betweenness = (
        nx.betweenness_centrality(graph, weight="distance", k=min(200, graph.number_of_nodes()), seed=42)
        if nx is not None and graph is not None and graph.number_of_nodes() > 1
        else {}
    )
    community_by_keyword: dict[str, int] = {}
    community_rows: list[dict[str, Any]] = []
    modularity = 0.0
    if nx is not None and graph is not None and graph.number_of_edges():
        communities = list(nx.algorithms.community.louvain_communities(graph, weight="weight", resolution=1.0, seed=42))
        modularity = nx.algorithms.community.modularity(graph, communities, weight="weight") if communities else 0.0
        for community_id, community in enumerate(communities):
            for keyword in community:
                community_by_keyword[str(keyword)] = community_id
            subgraph = graph.subgraph(community)
            top_keywords = [keyword for keyword, _ in sorted(subgraph.degree(weight="weight"), key=lambda item: item[1], reverse=True)[:8]]
            community_rows.append(
                {
                    "community_id": community_id,
                    "keyword_count": len(community),
                    "edge_count": subgraph.number_of_edges(),
                    "total_weight": round(sum(float(data.get("weight") or 0) for _, _, data in subgraph.edges(data=True)), 6),
                    "modularity": round(float(modularity), 6),
                    "top_keywords": "; ".join(str(keyword) for keyword in top_keywords),
                }
            )
    community_rows.sort(key=lambda row: (-int(row["keyword_count"]), -float(row["total_weight"])))

    metric_keywords = set(trend_by_keyword).union(degree)
    metric_rows: list[dict[str, Any]] = []
    for keyword in sorted(metric_keywords):
        trend = trend_by_keyword.get(keyword, {})
        metric_rows.append(
            {
                "keyword": keyword,
                "doc_count": int(trend.get("doc_count") or 0),
                "explicit_doc_count": int(trend.get("explicit_doc_count") or 0),
                "text_signal_doc_count": int(trend.get("text_signal_doc_count") or 0),
                "normalized_df": float(trend.get("normalized_df") or 0),
                "growth_rate": float(trend.get("growth_rate") or 0),
                "burst_score": float(trend.get("burst_score") or 0),
                "degree": round(float(degree.get(keyword, 0)), 6),
                "weighted_degree": round(float(degree.get(keyword, 0)), 6),
                "betweenness": round(float(betweenness.get(keyword, 0)), 6),
                "pagerank": round(float(pagerank.get(keyword, 0)), 6),
                "community_id": community_by_keyword.get(keyword, ""),
                "lifecycle_stage": stage_by_keyword.get(keyword, ""),
            }
        )
    metric_rows.sort(key=lambda row: (-float(row["pagerank"]), -float(row["weighted_degree"]), -int(row["doc_count"]), row["keyword"]))

    cache_rows = [
        {
            "method": "keyword_edge_cache_hits",
            "status": "final",
            "records": cache_hits,
            "note": "Papers whose keyword edge contributions were reused from cache.",
        },
        {
            "method": "keyword_edge_cache_misses",
            "status": "final",
            "records": cache_misses,
            "note": "Papers whose keyword edge contributions were recomputed.",
        },
    ]
    return edge_rows, metric_rows, community_rows, burst_rows, lifecycle_rows, drift_rows, cache_rows


def _build_keyword_extraction_assets(
    papers: list[dict[str, Any]],
    drift_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs = [
        str(paper.get("text_for_analysis") or "").strip()
        for paper in papers
        if _is_recent_year(paper.get("year")) and str(paper.get("text_for_analysis") or "").strip()
    ][:KEYWORD_EXTRACTION_SAMPLE_LIMIT]
    diagnostics = [
        {
            "method": "textrank",
            "status": "sample_only",
            "records": 0,
            "note": "TextRank is intentionally reserved for representative documents to avoid full-corpus graph cost.",
        },
        {
            "method": "keybert",
            "status": "optional_not_run",
            "records": 0,
            "note": "KeyBERT is treated as an optional reranker for selected candidates, not a required full-corpus pass.",
        },
        {
            "method": "semantic_drift",
            "status": "context_proxy",
            "records": len(drift_rows),
            "note": "Semantic drift uses keyword-context cosine proxy for top keywords.",
        },
    ]
    if not docs:
        diagnostics.append({"method": "tfidf", "status": "empty", "records": 0, "note": "No analyzable recent documents."})
        return [], diagnostics
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        rows = _fallback_tfidf_rows(docs)
        diagnostics.append(
            {
                "method": "tfidf",
                "status": "fallback",
                "records": len(rows),
                "note": "scikit-learn is not installed; used deterministic n-gram TF-IDF fallback.",
            }
        )
        return rows, diagnostics

    min_df = 1 if len(docs) < 20 else 5
    try:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=min_df,
            max_df=0.85,
            max_features=3000,
            stop_words="english",
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(docs)
    except ValueError as exc:
        diagnostics.append({"method": "tfidf", "status": "failed", "records": 0, "note": str(exc)})
        return [], diagnostics

    terms = vectorizer.get_feature_names_out()
    mean_scores = np.asarray(matrix.mean(axis=0)).ravel()
    doc_counts = np.asarray((matrix > 0).sum(axis=0)).ravel()
    order = np.argsort(mean_scores)[::-1][:120]
    rows = [
        {
            "term": _normalize_keyword(terms[index]),
            "method": "tfidf",
            "mean_tfidf": round(float(mean_scores[index]), 8),
            "doc_count": int(doc_counts[index]),
            "sample_documents": len(docs),
        }
        for index in order
        if _is_keyword_signal(str(terms[index]))
    ]
    if not rows:
        rows = _fallback_tfidf_rows(docs)
    diagnostics.append(
        {
            "method": "tfidf",
            "status": "final",
            "records": len(rows),
            "note": f"TF-IDF ran on {len(docs)} recent documents with max_features=3000.",
        }
    )
    return rows, diagnostics


def _fallback_tfidf_rows(docs: list[str]) -> list[dict[str, Any]]:
    stopwords = {
        "and",
        "are",
        "for",
        "from",
        "into",
        "that",
        "the",
        "their",
        "this",
        "with",
    }
    term_counts: Counter[str] = Counter()
    term_docs: Counter[str] = Counter()
    for doc in docs:
        tokens = [
            token
            for token in re.findall(r"[a-z][a-z0-9]+", _normalize_keyword(doc))
            if len(token) >= 3 and token not in stopwords
        ]
        terms: list[str] = []
        terms.extend(tokens)
        terms.extend(" ".join(tokens[index : index + 2]) for index in range(max(0, len(tokens) - 1)))
        terms.extend(" ".join(tokens[index : index + 3]) for index in range(max(0, len(tokens) - 2)))
        counts = Counter(term for term in terms if _is_keyword_signal(term))
        term_counts.update(counts)
        term_docs.update(counts.keys())
    scored_rows = []
    doc_total = max(len(docs), 1)
    for term, count in term_counts.items():
        doc_count = term_docs[term]
        idf = math.log((doc_total + 1) / (doc_count + 1)) + 1
        scored_rows.append(
            {
                "term": term,
                "method": "tfidf",
                "mean_tfidf": round((count / doc_total) * idf, 8),
                "doc_count": int(doc_count),
                "sample_documents": len(docs),
            }
        )
    scored_rows.sort(key=lambda row: (-float(row["mean_tfidf"]), -int(row["doc_count"]), row["term"]))
    return scored_rows[:120]


def _author_name_key(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return f"name:{normalized}" if normalized else ""


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _join_values(value: Any) -> str:
    values = _as_list(value)
    return "; ".join(dict.fromkeys(values))


def _top_counter_value(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _paper_author_entries(paper: dict[str, Any]) -> list[dict[str, Any]]:
    structured = paper.get("authorships") if isinstance(paper.get("authorships"), list) else []
    entries: list[dict[str, Any]] = []
    if structured:
        for index, authorship in enumerate(structured, start=1):
            display_name = str(authorship.get("display_name") or authorship.get("author") or authorship.get("raw_author_name") or "").strip()
            if not display_name:
                continue
            author_id = str(authorship.get("author_id") or "").strip()
            orcid = str(authorship.get("orcid") or "").strip()
            author_key = author_id or orcid or _author_name_key(display_name)
            if not author_key:
                continue
            entries.append(
                {
                    "author_key": author_key,
                    "author": display_name,
                    "author_id": author_id,
                    "raw_author_name": str(authorship.get("raw_author_name") or display_name).strip(),
                    "orcid": orcid,
                    "author_position": int(authorship.get("author_position_index") or index),
                    "author_role": str(authorship.get("author_position") or "").strip(),
                    "is_corresponding": bool(authorship.get("is_corresponding")),
                    "institution_ids": _as_list(authorship.get("institution_ids")),
                    "institutions": _as_list(authorship.get("institutions")),
                    "country_codes": _as_list(authorship.get("country_codes")),
                    "raw_affiliation_strings": _as_list(authorship.get("raw_affiliation_strings")),
                    "identity_source": "author_id" if author_id else "orcid" if orcid else "name",
                }
            )
        return entries

    for index, author in enumerate(paper.get("authors") or [], start=1):
        display_name = str(author).strip()
        author_key = _author_name_key(display_name)
        if not display_name or not author_key:
            continue
        entries.append(
            {
                "author_key": author_key,
                "author": display_name,
                "author_id": "",
                "raw_author_name": display_name,
                "orcid": "",
                "author_position": index,
                "author_role": "",
                "is_corresponding": False,
                "institution_ids": [],
                "institutions": [],
                "country_codes": [],
                "raw_affiliation_strings": [],
                "identity_source": "name",
            }
        )
    return entries


def _select_core_edge_rows(edge_rows: list[dict[str, Any]], nx_module: Any, *, max_edges: int) -> list[dict[str, Any]]:
    candidates = [row for row in edge_rows if int(row.get("long_author_papers") or 0) == 0][:max_edges]
    if not candidates or nx_module is None:
        return candidates
    pool_graph = nx_module.Graph()
    for row in candidates:
        pool_graph.add_edge(str(row["author_a_key"]), str(row["author_b_key"]))
    components = sorted(nx_module.connected_components(pool_graph), key=len, reverse=True)
    if not components:
        return candidates
    if len(components[0]) >= 30:
        selected_nodes = set(components[0])
    else:
        selected_nodes: set[str] = set()
        for component in components:
            if len(component) < 2:
                continue
            selected_nodes.update(component)
            if len(selected_nodes) >= 220:
                break
    selected = [
        row
        for row in candidates
        if str(row["author_a_key"]) in selected_nodes and str(row["author_b_key"]) in selected_nodes
    ]
    return selected or candidates


def _author_edge_signature(paper: dict[str, Any], unique_authors: list[dict[str, Any]]) -> str:
    return _stable_hash(
        {
            "paper_id": _doc_key(paper),
            "source": paper.get("source") or "",
            "year": paper.get("year") or "",
            "authors": [
                {
                    "author_key": entry["author_key"],
                    "author": entry["author"],
                    "author_id": entry.get("author_id") or "",
                }
                for entry in unique_authors
            ],
        }
    )


def _author_edge_contributions(
    unique_by_key: dict[str, dict[str, Any]],
    unique_authors: list[dict[str, Any]],
    year: int | None,
) -> list[dict[str, Any]]:
    if len(unique_authors) < 2:
        return []
    pair_weight = 1 / math.comb(len(unique_authors), 2)
    author_weight = 1 / (len(unique_authors) - 1)
    long_author_paper = int(len(unique_authors) > MAX_AUTHORS_FOR_CORE_NETWORK)
    contributions: list[dict[str, Any]] = []
    for entry_a, entry_b in combinations(unique_authors, 2):
        key = tuple(sorted((str(entry_a["author_key"]), str(entry_b["author_key"]))))
        row_a = unique_by_key[key[0]]
        row_b = unique_by_key[key[1]]
        contributions.append(
            {
                "author_a_key": key[0],
                "author_b_key": key[1],
                "author_a": row_a["author"],
                "author_b": row_b["author"],
                "paper_count": 1,
                "weight_full": 1.0,
                "weight_fraction_pair": pair_weight,
                "weight_fraction_author": author_weight,
                "year": year,
                "long_author_papers": long_author_paper,
            }
        )
    return contributions


def _merge_author_edge_contribution(
    edge_stats: dict[tuple[str, str], dict[str, Any]],
    author_collaborators: dict[str, set[str]],
    contribution: dict[str, Any],
) -> None:
    key = (str(contribution["author_a_key"]), str(contribution["author_b_key"]))
    year = _year_value(contribution.get("year"))
    stats = edge_stats.setdefault(
        key,
        {
            "author_a_key": key[0],
            "author_b_key": key[1],
            "author_a": contribution["author_a"],
            "author_b": contribution["author_b"],
            "paper_count": 0,
            "weight_full": 0.0,
            "weight_fraction_pair": 0.0,
            "weight_fraction_author": 0.0,
            "first_year": year,
            "last_year": year,
            "years": set(),
            "active_years": 0,
            "long_author_papers": 0,
        },
    )
    stats["paper_count"] += int(contribution.get("paper_count") or 1)
    stats["weight_full"] += float(contribution.get("weight_full") or 0)
    stats["weight_fraction_pair"] += float(contribution.get("weight_fraction_pair") or 0)
    stats["weight_fraction_author"] += float(contribution.get("weight_fraction_author") or 0)
    if year is not None:
        stats["years"].add(year)
        stats["first_year"] = min([item for item in (stats["first_year"], year) if item is not None])
        stats["last_year"] = max([item for item in (stats["last_year"], year) if item is not None])
    stats["long_author_papers"] += int(contribution.get("long_author_papers") or 0)
    author_collaborators[key[0]].add(key[1])
    author_collaborators[key[1]].add(key[0])


def _load_author_edge_aggregate(path: Path, author_collaborators: dict[str, set[str]]) -> dict[tuple[str, str], dict[str, Any]]:
    edge_stats: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.exists():
        return edge_stats
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            author_a_key = str(row.get("author_a_key") or "").strip()
            author_b_key = str(row.get("author_b_key") or "").strip()
            if not author_a_key or not author_b_key or author_a_key == author_b_key:
                continue
            key = tuple(sorted((author_a_key, author_b_key)))
            stats = {
                "author_a_key": key[0],
                "author_b_key": key[1],
                "author_a": str(row.get("author_a") or key[0]),
                "author_b": str(row.get("author_b") or key[1]),
                "paper_count": int(float(row.get("paper_count") or row.get("weight") or 0)),
                "weight_full": float(row.get("weight_full") or row.get("paper_count") or row.get("weight") or 0),
                "weight_fraction_pair": float(row.get("weight_fraction_pair") or 0),
                "weight_fraction_author": float(row.get("weight_fraction_author") or 0),
                "first_year": _year_value(row.get("first_year")),
                "last_year": _year_value(row.get("last_year")),
                "years": set(),
                "active_years": int(float(row.get("active_years") or 0)),
                "long_author_papers": int(float(row.get("long_author_papers") or 0)),
            }
            edge_stats[key] = stats
            author_collaborators[key[0]].add(key[1])
            author_collaborators[key[1]].add(key[0])
    return edge_stats


def _build_author_assets(
    papers: list[dict[str, Any]],
    *,
    edge_cache_dir: Path | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    try:
        import networkx as nx
    except ImportError:
        nx = None

    paper_authors: list[dict[str, Any]] = []
    author_years: dict[str, Counter[int]] = defaultdict(Counter)
    author_fields: dict[str, Counter[str]] = defaultdict(Counter)
    author_collaborators: dict[str, set[str]] = defaultdict(set)
    author_profiles: dict[str, dict[str, Any]] = {}
    skipped_long_author_papers = 0
    papers_with_authors = 0
    papers_with_structured_authorships = 0
    author_mentions = 0
    author_mentions_with_id = 0
    author_edge_cache_hits = 0
    author_edge_cache_misses = 0
    author_edge_cache_path = edge_cache_dir / "author_edge_papers.jsonl" if edge_cache_dir else None
    previous_edge_path = edge_cache_dir.parent / "author_collaboration_edges.csv" if edge_cache_dir else None
    author_edge_cache = _load_incremental_cache(author_edge_cache_path) if author_edge_cache_path else {}
    author_edge_records: list[dict[str, Any]] = []
    current_cache_keys: set[str] = set()
    cache_changed = False

    for paper in papers:
        paper_id = str(paper.get("paper_id") or "")
        source = str(paper.get("source") or "")
        year = _year_value(paper.get("year"))
        author_entries = _paper_author_entries(paper)
        if author_entries:
            papers_with_authors += 1
        if isinstance(paper.get("authorships"), list) and paper.get("authorships"):
            papers_with_structured_authorships += 1
        unique_by_key = {entry["author_key"]: entry for entry in author_entries}
        unique_authors = [unique_by_key[key] for key in sorted(unique_by_key)]
        for entry in author_entries:
            author_mentions += 1
            if entry["author_id"]:
                author_mentions_with_id += 1
            author_key = str(entry["author_key"])
            profile = author_profiles.setdefault(
                author_key,
                {
                    "author_key": author_key,
                    "author": entry["author"],
                    "author_id": entry["author_id"],
                    "raw_author_names": Counter(),
                    "orcid": entry["orcid"],
                    "institution_ids": Counter(),
                    "institutions": Counter(),
                    "country_codes": Counter(),
                    "raw_affiliation_strings": Counter(),
                    "identity_source": entry["identity_source"],
                },
            )
            profile["raw_author_names"][entry["raw_author_name"]] += int(bool(entry["raw_author_name"]))
            for field_name in ("institution_ids", "institutions", "country_codes", "raw_affiliation_strings"):
                profile[field_name].update(entry[field_name])
            if not profile["orcid"] and entry["orcid"]:
                profile["orcid"] = entry["orcid"]
            if profile["identity_source"] == "name" and entry["identity_source"] != "name":
                profile["identity_source"] = entry["identity_source"]
            paper_authors.append(
                {
                    "paper_id": paper_id,
                    "source": source,
                    "year": paper.get("year") or "",
                    "author_key": author_key,
                    "author": entry["author"],
                    "author_id": entry["author_id"],
                    "raw_author_name": entry["raw_author_name"],
                    "orcid": entry["orcid"],
                    "author_position": entry["author_position"],
                    "author_role": entry["author_role"],
                    "is_corresponding": entry["is_corresponding"],
                    "institution_ids": _join_values(entry["institution_ids"]),
                    "institutions": _join_values(entry["institutions"]),
                    "country_codes": _join_values(entry["country_codes"]),
                    "raw_affiliation_strings": _join_values(entry["raw_affiliation_strings"]),
                    "identity_source": entry["identity_source"],
                }
            )
            if year is not None:
                author_years[author_key][year] += 1
            author_fields[author_key][str(paper.get("field_seed") or paper.get("field") or "unknown")] += 1
        if len(unique_authors) > MAX_AUTHORS_FOR_CORE_NETWORK:
            skipped_long_author_papers += 1
        if len(unique_authors) < 2:
            continue
        signature = _author_edge_signature(paper, unique_authors)
        cache_key = f"{source}:{_doc_key(paper)}"
        current_cache_keys.add(cache_key)
        cached = author_edge_cache.get(cache_key)
        cache_hit = bool(cached and cached.get("signature") == signature)
        if cached and not cache_hit:
            cache_changed = True
        author_edge_records.append({"cache_key": cache_key, "paper_id": _doc_key(paper), "source": source, "signature": signature, "cache_hit": cache_hit})

    cache_removed = bool(set(author_edge_cache) - current_cache_keys)
    can_reuse_previous_edges = bool(author_edge_cache) and bool(previous_edge_path and previous_edge_path.exists()) and not cache_changed and not cache_removed
    edge_stats = _load_author_edge_aggregate(previous_edge_path, author_collaborators) if can_reuse_previous_edges and previous_edge_path else {}

    signature_by_cache_key = {record["cache_key"]: record for record in author_edge_records}
    for paper in papers:
        source = str(paper.get("source") or "")
        cache_key = f"{source}:{_doc_key(paper)}"
        record = signature_by_cache_key.get(cache_key)
        if record is None:
            continue
        if can_reuse_previous_edges and record["cache_hit"]:
            author_edge_cache_hits += 1
            continue
        author_entries = _paper_author_entries(paper)
        unique_by_key = {entry["author_key"]: entry for entry in author_entries}
        unique_authors = [unique_by_key[key] for key in sorted(unique_by_key)]
        contributions = _author_edge_contributions(unique_by_key, unique_authors, _year_value(paper.get("year")))
        author_edge_cache_misses += 1
        for contribution in contributions:
            _merge_author_edge_contribution(edge_stats, author_collaborators, contribution)

    if author_edge_cache_path:
        _write_incremental_cache(
            author_edge_cache_path,
            (
                {
                    "cache_version": INCREMENTAL_CACHE_VERSION,
                    "cache_key": record["cache_key"],
                    "paper_id": record["paper_id"],
                    "source": record["source"],
                    "signature": record["signature"],
                }
                for record in author_edge_records
            ),
        )

    edge_rows: list[dict[str, Any]] = []
    for stats in edge_stats.values():
        row = {
            "author_a_key": stats["author_a_key"],
            "author_b_key": stats["author_b_key"],
            "author_a": stats["author_a"],
            "author_b": stats["author_b"],
            "weight": int(stats["paper_count"]),
            "paper_count": int(stats["paper_count"]),
            "weight_full": round(float(stats["weight_full"]), 6),
            "weight_fraction_pair": round(float(stats["weight_fraction_pair"]), 6),
            "weight_fraction_author": round(float(stats["weight_fraction_author"]), 6),
            "first_year": stats["first_year"] or "",
            "last_year": stats["last_year"] or "",
            "active_years": max(len(stats["years"]), int(stats.get("active_years") or 0)),
            "long_author_papers": int(stats["long_author_papers"]),
        }
        edge_rows.append(row)
    edge_rows.sort(
        key=lambda row: (
            -float(row["weight_fraction_pair"]),
            -int(row["paper_count"]),
            row["author_a_key"],
            row["author_b_key"],
        )
    )
    graph = nx.Graph() if nx is not None else None
    if graph is not None:
        core_rows = _select_core_edge_rows(edge_rows, nx, max_edges=MAX_CORE_AUTHOR_GRAPH_EDGES)
        for row in core_rows:
            weight = float(row["weight_fraction_pair"])
            graph.add_edge(str(row["author_a_key"]), str(row["author_b_key"]), weight=weight, distance=1 / weight if weight else 1)

    degree = dict(graph.degree(weight="weight")) if graph is not None and graph.number_of_nodes() else {}
    betweenness = (
        nx.betweenness_centrality(graph, weight="distance", k=min(200, graph.number_of_nodes()), seed=42)
        if nx is not None and graph is not None and graph.number_of_nodes() > 1
        else {}
    )
    try:
        eigenvector = nx.eigenvector_centrality(graph, weight="weight", max_iter=300) if nx is not None and graph is not None and graph.number_of_nodes() > 1 else {}
    except Exception:
        eigenvector = {}
    pagerank = (
        nx.pagerank(graph, weight="weight")
        if nx is not None and graph is not None and graph.number_of_nodes() > 1
        else {}
    )
    try:
        core_number = nx.core_number(graph) if nx is not None and graph is not None and graph.number_of_edges() else {}
    except Exception:
        core_number = {}

    communities = []
    sensitivity_rows: list[dict[str, Any]] = []
    community_by_author: dict[str, int] = {}
    best_resolution = ""
    best_modularity = 0.0
    if nx is not None and graph is not None and graph.number_of_edges():
        best_score = (-1.0, 0)
        best_communities: list[set[str]] = []
        for resolution in (0.8, 1.0, 1.2):
            found = list(nx.algorithms.community.louvain_communities(graph, weight="weight", resolution=resolution, seed=42))
            modularity = nx.algorithms.community.modularity(graph, found, weight="weight") if found else 0.0
            sensitivity_rows.append(
                {
                    "resolution": resolution,
                    "communities": len(found),
                    "modularity": round(float(modularity), 6),
                }
            )
            score = (modularity, -abs(len(found) - math.sqrt(max(graph.number_of_nodes(), 1))))
            if score > best_score:
                best_score = score
                best_communities = [set(item) for item in found]
                best_resolution = str(resolution)
                best_modularity = float(modularity)
        for community_id, community in enumerate(best_communities):
            for author_key in community:
                community_by_author[author_key] = community_id
            subgraph = graph.subgraph(community)
            top_author_keys = sorted(subgraph.degree(weight="weight"), key=lambda item: item[1], reverse=True)[:5]
            top_authors = [str(author_profiles.get(author_key, {}).get("author") or author_key) for author_key, _ in top_author_keys]
            communities.append(
                {
                    "community_id": community_id,
                    "resolution": best_resolution,
                    "modularity": round(best_modularity, 6),
                    "author_count": len(community),
                    "edge_count": subgraph.number_of_edges(),
                    "total_weight": round(sum(float(data.get("weight") or 0) for _, _, data in subgraph.edges(data=True)), 6),
                    "top_authors": "; ".join(top_authors),
                }
            )
    communities.sort(key=lambda row: (-int(row["author_count"]), -float(row["total_weight"])))

    metrics_rows: list[dict[str, Any]] = []
    for author in sorted(set(author_years).union(author_collaborators)):
        years = author_years.get(author, Counter())
        fields = author_fields.get(author, Counter())
        profile = author_profiles.get(author, {})
        metrics_rows.append(
            {
                "author_key": author,
                "author": profile.get("author", author),
                "author_id": profile.get("author_id", ""),
                "orcid": profile.get("orcid", ""),
                "raw_author_names": "; ".join(name for name, _ in profile.get("raw_author_names", Counter()).most_common(3)),
                "paper_count": sum(years.values()),
                "collaborator_count": len(author_collaborators.get(author, set())),
                "degree": round(float(degree.get(author, 0)), 6),
                "weighted_degree": round(float(degree.get(author, 0)), 6),
                "betweenness": round(float(betweenness.get(author, 0)), 6),
                "eigenvector": round(float(eigenvector.get(author, 0)), 6),
                "pagerank": round(float(pagerank.get(author, 0)), 6),
                "core_number": int(core_number.get(author, 0)),
                "community_id": community_by_author.get(author, ""),
                "first_year": min(years) if years else "",
                "last_year": max(years) if years else "",
                "active_years": len(years),
                "dominant_field": _top_counter_value(fields),
                "institution_ids": "; ".join(value for value, _ in profile.get("institution_ids", Counter()).most_common(3)),
                "institutions": "; ".join(value for value, _ in profile.get("institutions", Counter()).most_common(3)),
                "country_codes": "; ".join(value for value, _ in profile.get("country_codes", Counter()).most_common(3)),
                "identity_source": profile.get("identity_source", "name"),
            }
        )
    metrics_rows.sort(key=lambda row: (-float(row["betweenness"]), -float(row["degree"]), -int(row["paper_count"]), row["author"]))

    by_year_rows = [
        {"author_key": author, "author": str(author_profiles.get(author, {}).get("author") or author), "year": year, "paper_count": count}
        for author, years in sorted(author_years.items())
        for year, count in sorted(years.items())
    ]

    diagnostics = [
        {"metric": "papers_with_authors", "value": papers_with_authors, "note": "Records with at least one usable author."},
        {
            "metric": "papers_with_structured_authorships",
            "value": papers_with_structured_authorships,
            "note": "Records carrying source-level authorship metadata.",
        },
        {"metric": "author_mentions", "value": author_mentions, "note": "Paper-author rows before per-paper deduplication."},
        {"metric": "author_mentions_with_id", "value": author_mentions_with_id, "note": "Author mentions backed by persistent source IDs."},
        {"metric": "unique_author_keys", "value": len(author_profiles), "note": "Distinct author entities after ID/name keying."},
        {"metric": "coauthor_edges", "value": len(edge_rows), "note": "Distinct coauthor entity pairs."},
        {"metric": "long_author_papers", "value": skipped_long_author_papers, "note": "Papers above the core-network author threshold."},
        {
            "metric": "core_graph_edges",
            "value": graph.number_of_edges() if graph is not None else 0,
            "note": "Edges used for centrality and community diagnostics.",
        },
        {
            "metric": "core_graph_nodes",
            "value": graph.number_of_nodes() if graph is not None else 0,
            "note": "Author entities present in the core graph.",
        },
        {"metric": "louvain_resolution", "value": best_resolution, "note": "Selected by modularity over tested resolutions."},
        {"metric": "louvain_modularity", "value": round(best_modularity, 6), "note": "Modularity of selected Louvain partition."},
        {"metric": "louvain_communities", "value": len(communities), "note": "Communities in selected core graph partition."},
        {"metric": "author_edge_cache_hits", "value": author_edge_cache_hits, "note": "Papers whose coauthor edge contributions were reused from cache."},
        {"metric": "author_edge_cache_misses", "value": author_edge_cache_misses, "note": "Papers whose coauthor edge contributions were recomputed."},
    ]
    return paper_authors, edge_rows, metrics_rows, by_year_rows, communities, diagnostics, sensitivity_rows


def _build_topic_assets(papers: list[dict[str, Any]], *, max_topics: int = 8) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    docs = [
        paper
        for paper in papers
        if _is_recent_year(paper.get("year")) and len(str(paper.get("text_for_analysis") or "").split()) >= 5
    ][:TOPIC_SAMPLE_LIMIT]
    if len(docs) < 2:
        return [], [], [], []
    try:
        from sklearn.decomposition import LatentDirichletAllocation, NMF
        from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
    except ImportError:
        return [], [], [], []

    texts = [str(paper.get("text_for_analysis") or "") for paper in docs]
    topic_count = max(2, min(max_topics, len(docs) // 2))
    comparison_rows: list[dict[str, Any]] = []
    keyword_rows: list[dict[str, Any]] = []
    paper_topic_rows: list[dict[str, Any]] = []
    topic_year_counts: dict[tuple[str, int, int], int] = defaultdict(int)

    model_specs = [
        ("lda", CountVectorizer(max_features=1400, min_df=2, max_df=0.82, stop_words="english"), LatentDirichletAllocation(n_components=topic_count, random_state=42, learning_method="batch", max_iter=8)),
        ("nmf", TfidfVectorizer(max_features=1400, min_df=2, max_df=0.82, stop_words="english"), NMF(n_components=topic_count, random_state=42, init="nndsvda", max_iter=220)),
    ]
    for model_name, vectorizer, model in model_specs:
        try:
            matrix = vectorizer.fit_transform(texts)
            transformed = model.fit_transform(matrix)
        except ValueError:
            continue
        terms = vectorizer.get_feature_names_out()
        comparison_rows.append(
            {
                "model": model_name,
                "topics": topic_count,
                "documents": len(docs),
                "vocabulary": len(terms),
                "quality_proxy": round(float(getattr(model, "reconstruction_err_", 0) or getattr(model, "bound_", 0) or 0), 6),
            }
        )
        for topic_id, component in enumerate(model.components_):
            top_indices = np.argsort(component)[::-1][:12] if "np" in globals() else sorted(range(len(component)), key=lambda index: component[index], reverse=True)[:12]
            words = [str(terms[index]) for index in top_indices]
            keyword_rows.append({"model": model_name, "topic_id": topic_id, "ranked_keywords": "; ".join(words)})
        for paper, weights in zip(docs, transformed, strict=False):
            topic_id = int(max(range(len(weights)), key=lambda index: weights[index]))
            year = _year_value(paper.get("year"))
            if year is not None:
                topic_year_counts[(model_name, topic_id, year)] += 1
            if model_name == "nmf":
                paper_topic_rows.append(
                    {
                        "paper_id": paper.get("paper_id") or "",
                        "source": paper.get("source") or "",
                        "year": paper.get("year") or "",
                        "model": model_name,
                        "topic_id": topic_id,
                        "topic_weight": round(float(weights[topic_id]), 6),
                    }
                )
    topic_year_rows = [
        {"model": model, "topic_id": topic_id, "year": year, "paper_count": count}
        for (model, topic_id, year), count in sorted(topic_year_counts.items())
    ]
    return comparison_rows, keyword_rows, paper_topic_rows, topic_year_rows


def build_analysis_assets(
    *,
    raw_dir: str | Path = "data/raw",
    output_dir: str | Path = "data/analysis",
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    filename_template: str | None = None,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    edge_cache_dir = output_path / ".incremental"
    collection_rows, collection_summary = _build_collection_manifest(raw_path, sources, filename_template)

    papers: list[dict[str, Any]] = []
    paper_taxonomy: list[dict[str, Any]] = []
    seen: set[str] = set()
    input_records = 0
    duplicates = 0
    invalid_records = 0

    for wrapper in _iter_wrappers(raw_path, sources=sources, filename_template=filename_template):
        input_records += 1
        if wrapper is None:
            invalid_records += 1
            continue
        try:
            paper = _paper_with_source(wrapper)
        except (ValueError, TypeError, KeyError):
            invalid_records += 1
            continue
        key = _dedupe_key(paper, wrapper)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        papers.append(paper)
        paper_taxonomy.append(_taxonomy_for_paper(wrapper, paper))

    (
        paper_keywords,
        paper_keyword_signals,
        keyword_year_rows,
        keyword_trend_rows,
        keyword_alias_rows,
        keyword_edge_rows,
        keyword_metrics_rows,
        keyword_community_rows,
        keyword_burst_rows,
        keyword_lifecycle_rows,
        keyword_drift_rows,
        keyword_tfidf_rows,
        keyword_extraction_diagnostics_rows,
    ) = _build_keyword_assets(papers, edge_cache_dir=edge_cache_dir)
    (
        paper_authors,
        edge_rows,
        author_metrics_rows,
        author_metrics_by_year_rows,
        author_community_rows,
        author_network_diagnostics_rows,
        author_louvain_sensitivity_rows,
    ) = _build_author_assets(papers, edge_cache_dir=edge_cache_dir)
    topic_comparison_rows, topic_keyword_rows, paper_topic_rows, topic_year_share_rows = _build_topic_assets(papers, max_topics=40)
    taxonomy_coverage_rows = _build_taxonomy_coverage(paper_taxonomy)

    quality_by_source: dict[str, dict[str, int | str]] = defaultdict(
        lambda: {
            "source": "",
            "records": 0,
            "title_count": 0,
            "abstract_count": 0,
            "authors_count": 0,
            "year_count": 0,
            "keywords_count": 0,
            "full_text_count": 0,
        }
    )
    for paper in papers:
        source = str(paper.get("source") or "unknown")
        row = quality_by_source[source]
        row["source"] = source
        row["records"] = int(row["records"]) + 1
        row["title_count"] = int(row["title_count"]) + int(bool(paper.get("title")))
        row["abstract_count"] = int(row["abstract_count"]) + int(bool(paper.get("abstract")))
        row["authors_count"] = int(row["authors_count"]) + int(bool(paper.get("authors")))
        row["year_count"] = int(row["year_count"]) + int(bool(paper.get("year")))
        row["keywords_count"] = int(row["keywords_count"]) + int(bool(paper.get("keywords")))
        row["full_text_count"] = int(row["full_text_count"]) + int(bool(paper.get("full_text")))

    quality_rows = [quality_by_source[source] for source in sorted(quality_by_source)]

    output_path.joinpath("papers_clean.json").write_text(
        json.dumps(papers, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        output_path / "collection_manifest.csv",
        collection_rows,
        [
            "source",
            "year_partition",
            "file",
            "records",
            "file_size_bytes",
            "empty_file",
            "invalid_json_lines",
            "observed_years",
            "abnormal_years",
        ],
    )
    _write_csv(
        output_path / "paper_authors.csv",
        paper_authors,
        [
            "paper_id",
            "source",
            "year",
            "author_key",
            "author",
            "author_id",
            "raw_author_name",
            "orcid",
            "author_position",
            "author_role",
            "is_corresponding",
            "institution_ids",
            "institutions",
            "country_codes",
            "raw_affiliation_strings",
            "identity_source",
        ],
    )
    _write_csv(
        output_path / "paper_keywords.csv",
        paper_keywords,
        ["paper_id", "source", "year", "keyword"],
    )
    _write_csv(
        output_path / "paper_keyword_signals.csv",
        paper_keyword_signals,
        ["paper_id", "source", "year", "keyword", "signal_source"],
    )
    _write_csv(
        output_path / "keyword_year_matrix.csv",
        keyword_year_rows,
        [
            "keyword",
            "year",
            "count",
            "explicit_count",
            "text_signal_count",
            "total_docs_in_year",
            "analyzable_docs_in_year",
            "normalized_df",
        ],
    )
    keyword_trend_fields = [
        "keyword",
        "doc_count",
        "explicit_doc_count",
        "text_signal_doc_count",
        "normalized_df",
        "growth_rate",
        "momentum_score",
        "burst_score",
        "ytd_2026_normalized_df",
        "representative_paper_id",
        "representative_title",
        "representative_year",
    ]
    for year in range(RECENT_YEAR_START, RECENT_YEAR_END + 1):
        keyword_trend_fields.extend(
            [
                f"doc_count_{year}",
                f"explicit_count_{year}",
                f"text_signal_count_{year}",
                f"normalized_df_{year}",
            ]
        )
    _write_csv(output_path / "keyword_trends.csv", keyword_trend_rows, keyword_trend_fields)
    _write_csv(output_path / "keyword_aliases.csv", keyword_alias_rows, ["raw_keyword", "canonical_keyword"])
    _write_csv(
        output_path / "keyword_cooccurrence_edges.csv",
        keyword_edge_rows,
        ["keyword_a", "keyword_b", "weight", "paper_count", "first_year", "last_year", "active_years"],
    )
    _write_csv(
        output_path / "keyword_metrics.csv",
        keyword_metrics_rows,
        [
            "keyword",
            "doc_count",
            "explicit_doc_count",
            "text_signal_doc_count",
            "normalized_df",
            "growth_rate",
            "burst_score",
            "degree",
            "weighted_degree",
            "betweenness",
            "pagerank",
            "community_id",
            "lifecycle_stage",
        ],
    )
    _write_csv(
        output_path / "keyword_communities.csv",
        keyword_community_rows,
        ["community_id", "keyword_count", "edge_count", "total_weight", "modularity", "top_keywords"],
    )
    _write_csv(
        output_path / "keyword_burst_windows.csv",
        keyword_burst_rows,
        [
            "keyword",
            "year",
            "previous_year",
            "count",
            "previous_count",
            "normalized_df",
            "previous_normalized_df",
            "growth_rate",
            "burst_score",
            "burst_state",
        ],
    )
    _write_csv(
        output_path / "keyword_lifecycle.csv",
        keyword_lifecycle_rows,
        ["keyword", "lifecycle_stage", "doc_count", "first_year", "peak_year", "last_year", "peak_count", "growth_rate", "burst_score"],
    )
    _write_csv(
        output_path / "keyword_semantic_drift.csv",
        keyword_drift_rows,
        ["keyword", "year_from", "year_to", "cosine_similarity", "drift_score", "method", "significant"],
    )
    _write_csv(
        output_path / "keyword_tfidf_terms.csv",
        keyword_tfidf_rows,
        ["term", "method", "mean_tfidf", "doc_count", "sample_documents"],
    )
    _write_csv(
        output_path / "keyword_extraction_diagnostics.csv",
        keyword_extraction_diagnostics_rows,
        ["method", "status", "records", "note"],
    )
    _write_csv(
        output_path / "paper_taxonomy.csv",
        paper_taxonomy,
        [
            "paper_id",
            "source",
            "year",
            "domain",
            "field",
            "subfield",
            "taxonomy_source",
            "taxonomy_confidence",
            "raw_taxonomy_terms",
            "has_full_text",
        ],
    )
    _write_csv(
        output_path / "source_taxonomy_coverage.csv",
        taxonomy_coverage_rows,
        ["source", "domain", "field", "subfield", "records", "full_text_count", "full_text_rate"],
    )
    _write_csv(
        output_path / "author_collaboration_edges.csv",
        edge_rows,
        [
            "author_a_key",
            "author_b_key",
            "author_a",
            "author_b",
            "weight",
            "paper_count",
            "weight_full",
            "weight_fraction_pair",
            "weight_fraction_author",
            "first_year",
            "last_year",
            "active_years",
            "long_author_papers",
        ],
    )
    _write_csv(
        output_path / "author_metrics.csv",
        author_metrics_rows,
        [
            "author_key",
            "author",
            "author_id",
            "orcid",
            "raw_author_names",
            "paper_count",
            "collaborator_count",
            "degree",
            "weighted_degree",
            "betweenness",
            "eigenvector",
            "pagerank",
            "core_number",
            "community_id",
            "first_year",
            "last_year",
            "active_years",
            "dominant_field",
            "institution_ids",
            "institutions",
            "country_codes",
            "identity_source",
        ],
    )
    _write_csv(output_path / "author_metrics_by_year.csv", author_metrics_by_year_rows, ["author_key", "author", "year", "paper_count"])
    _write_csv(
        output_path / "author_communities.csv",
        author_community_rows,
        ["community_id", "resolution", "modularity", "author_count", "edge_count", "total_weight", "top_authors"],
    )
    _write_csv(output_path / "author_network_diagnostics.csv", author_network_diagnostics_rows, ["metric", "value", "note"])
    _write_csv(output_path / "author_louvain_sensitivity.csv", author_louvain_sensitivity_rows, ["resolution", "communities", "modularity"])
    _write_csv(output_path / "topic_model_comparison.csv", topic_comparison_rows, ["model", "topics", "documents", "vocabulary", "quality_proxy"])
    _write_csv(output_path / "topic_keywords.csv", topic_keyword_rows, ["model", "topic_id", "ranked_keywords"])
    _write_csv(output_path / "paper_topics.csv", paper_topic_rows, ["paper_id", "source", "year", "model", "topic_id", "topic_weight"])
    _write_csv(output_path / "topic_year_share.csv", topic_year_share_rows, ["model", "topic_id", "year", "paper_count"])
    _write_csv(
        output_path / "source_quality_report.csv",
        quality_rows,
        [
            "source",
            "records",
            "title_count",
            "abstract_count",
            "authors_count",
            "year_count",
            "keywords_count",
            "full_text_count",
        ],
    )

    author_diagnostic_values = {str(row.get("metric") or ""): row.get("value") for row in author_network_diagnostics_rows}
    keyword_diagnostic_values = {str(row.get("method") or ""): row.get("records") for row in keyword_extraction_diagnostics_rows}

    summary = {
        "input_records": input_records,
        "papers": len(papers),
        "duplicates": duplicates,
        "invalid_records": invalid_records,
        **collection_summary,
        "sources": sorted({paper.get("source") for paper in papers if paper.get("source")}),
        "paper_authors": len(paper_authors),
        "paper_keywords": len(paper_keywords),
        "paper_taxonomy": len(paper_taxonomy),
        "taxonomy_coverage_rows": len(taxonomy_coverage_rows),
        "paper_keyword_signals": len(paper_keyword_signals),
        "keyword_year_rows": len(keyword_year_rows),
        "keyword_trends": len(keyword_trend_rows),
        "keyword_edges": len(keyword_edge_rows),
        "keyword_metrics": len(keyword_metrics_rows),
        "keyword_communities": len(keyword_community_rows),
        "keyword_burst_windows": len(keyword_burst_rows),
        "keyword_lifecycle": len(keyword_lifecycle_rows),
        "keyword_semantic_drift": len(keyword_drift_rows),
        "keyword_tfidf_terms": len(keyword_tfidf_rows),
        "keyword_extraction_diagnostics": len(keyword_extraction_diagnostics_rows),
        "keyword_edge_cache_hits": int(keyword_diagnostic_values.get("keyword_edge_cache_hits") or 0),
        "keyword_edge_cache_misses": int(keyword_diagnostic_values.get("keyword_edge_cache_misses") or 0),
        "author_edges": len(edge_rows),
        "author_metrics": len(author_metrics_rows),
        "author_communities": len(author_community_rows),
        "author_network_diagnostics": len(author_network_diagnostics_rows),
        "author_louvain_sensitivity": len(author_louvain_sensitivity_rows),
        "author_edge_cache_hits": int(author_diagnostic_values.get("author_edge_cache_hits") or 0),
        "author_edge_cache_misses": int(author_diagnostic_values.get("author_edge_cache_misses") or 0),
        "topic_models": len(topic_comparison_rows),
        "topic_keywords": len(topic_keyword_rows),
        "recent_year_start": RECENT_YEAR_START,
        "recent_year_end": RECENT_YEAR_END,
        "recent_papers": sum(1 for paper in papers if _is_recent_year(paper.get("year"))),
        "max_authors_for_core_network": MAX_AUTHORS_FOR_CORE_NETWORK,
        "max_core_author_graph_edges": MAX_CORE_AUTHOR_GRAPH_EDGES,
    }
    output_path.joinpath("summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
