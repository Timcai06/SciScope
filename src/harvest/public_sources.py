from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from http.client import IncompleteRead, RemoteDisconnected
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from src.harvest.openalex_client import DEFAULT_QUERIES, harvest_openalex


SUPPORTED_SOURCES = (
    "openalex",
    "arxiv",
    "pubmed",
    "pmc",
    "crossref",
    "semantic_scholar",
    "doaj",
    "core",
)

BACKFILL_QUERIES = [
    ("computer science", "machine learning"),
    ("computer science", "artificial intelligence"),
    ("computer science", "deep learning"),
    ("biomedicine", "cancer"),
    ("biomedicine", "clinical trial"),
    ("biomedicine", "bioinformatics"),
    ("materials science", "materials science"),
    ("materials science", "nanomaterials"),
    ("materials science", "energy materials"),
]

PMC_QUERIES = [
    ("biomedicine", "cancer"),
    ("biomedicine", "diabetes"),
    ("biomedicine", "clinical trial"),
    ("biomedicine", "public health"),
    ("biomedicine", "covid-19"),
    ("biomedicine", "bioinformatics"),
    ("biomedicine", "drug discovery"),
    ("biomedicine", "genomics"),
    ("biomedicine", "neuroscience"),
    ("biomedicine", "machine learning medicine"),
]

PMC_BACKFILL_QUERIES = [
    ("biomedicine", "healthcare"),
    ("biomedicine", "epidemiology"),
    ("biomedicine", "immunology"),
    ("biomedicine", "precision medicine"),
    ("biomedicine", "mental health"),
    ("biomedicine", "cardiovascular disease"),
    ("biomedicine", "infectious disease"),
    ("biomedicine", "nutrition"),
    ("biomedicine", "primary care"),
    ("biomedicine", "systematic review"),
    ("biomedicine", "genetics"),
]

ARXIV_URL = "https://export.arxiv.org/api/query"
NCBI_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NCBI_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CROSSREF_URL = "https://api.crossref.org/works"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
DOAJ_URL = "https://doaj.org/api/search/articles"
CORE_URL = "https://api.core.ac.uk/v3/search/works"
ARXIV_BATCH_SIZE = 100
ARXIV_SLEEP_SECONDS = 5.0
NCBI_EFETCH_BATCH_SIZE = 100
NCBI_ESUMMARY_BATCH_SIZE = 200
CROSSREF_BATCH_SIZE = 1000
DOAJ_BATCH_SIZE = 100
DOAJ_QUERY_RESULT_CAP = 1000


class HarvestError(RuntimeError):
    """Raised when a public source harvest fails."""


def _progress(message: str) -> None:
    print(f"[harvest] {message}", file=sys.stderr, flush=True)


def _batched(values: list[str], size: int):
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def default_raw_path(source: str, limit: int) -> Path:
    return Path("data") / "raw" / source / f"{source}_{limit}.jsonl"


def year_raw_path(source: str, year: int, limit: int) -> Path:
    return Path("data") / "raw" / source / f"{source}_{year}_{limit}.jsonl"


def _request_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    query = urlencode({key: value for key, value in (params or {}).items() if value not in {None, ""}})
    target = f"{url}?{query}" if query else url
    request = Request(target, data=data, headers={"User-Agent": "SciScopeHarvester/0.1", **(headers or {})})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = HarvestError(f"{url} HTTP {exc.code}: {body[:400]}")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise last_error from exc
            time.sleep(float(exc.headers.get("Retry-After") or attempt * 10))
        except (TimeoutError, URLError, IncompleteRead, RemoteDisconnected) as exc:
            last_error = HarvestError(f"{url} request failed: {exc}")
            if attempt == 3:
                raise last_error from exc
            time.sleep(attempt * 3)
    raise HarvestError(f"{url} request failed: {last_error}")


def _request_xml(url: str, params: dict[str, Any], *, timeout: int = 45) -> ET.Element:
    query = urlencode({key: value for key, value in params.items() if value not in {None, ""}})
    request = Request(f"{url}?{query}", headers={"User-Agent": "SciScopeHarvester/0.1"})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=timeout) as response:
                return ET.fromstring(response.read())
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = HarvestError(f"{url} HTTP {exc.code}: {body[:400]}")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise last_error from exc
            time.sleep(float(exc.headers.get("Retry-After") or attempt * 10))
        except (TimeoutError, URLError, IncompleteRead, RemoteDisconnected, ET.ParseError) as exc:
            last_error = HarvestError(f"{url} request failed: {exc}")
            if attempt == 3:
                raise last_error from exc
            time.sleep(attempt * 3)
    raise HarvestError(f"{url} request failed: {last_error}")


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join(part.strip() for part in node.itertext() if part.strip())


def _year_from_text(value: Any) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _first_text(parent: ET.Element, paths: list[str]) -> str:
    for path in paths:
        value = _text(parent.find(path))
        if value:
            return value
    return ""


def _write_wrappers(
    *,
    output_path: str | Path,
    source: str,
    limit: int,
    fetch_query: Callable[[str, str, int], list[dict[str, Any]]],
    queries: list[tuple[str, str]] | None = None,
    backfill_queries: list[tuple[str, str]] | None = None,
    backfill_fetch_query: Callable[[str, str, int], list[dict[str, Any]]] | None = None,
    backfill_min_query_limit: int = 0,
) -> int:
    if limit <= 0:
        raise ValueError("limit must be positive")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    query_plan = queries or DEFAULT_QUERIES
    backfill_plan = backfill_queries or BACKFILL_QUERIES
    target_per_query = max(1, (limit + len(query_plan) - 1) // len(query_plan))
    seen: set[str] = set()
    written = 0
    existing_records = _line_count(output)
    _progress(f"{source}: start limit={limit} output={output}")
    temp_output = output.with_name(f"{output.name}.tmp")

    with temp_output.open("w", encoding="utf-8") as handle:
        def write_items(
            field: str,
            query: str,
            query_limit: int,
            fetcher: Callable[[str, str, int], list[dict[str, Any]]],
        ) -> int:
            nonlocal written
            before = written
            for item in fetcher(field, query, query_limit):
                source_id = str(item.get("source_id") or "").strip()
                if not source_id or source_id in seen:
                    continue
                seen.add(source_id)
                wrapper = {
                    "source": source,
                    "source_id": source_id,
                    "query": query,
                    "field_seed": field,
                    "crawled_at": utc_now(),
                    "raw": item.get("raw") or item,
                }
                handle.write(json.dumps(wrapper, ensure_ascii=False) + "\n")
                written += 1
                if written >= limit:
                    break
            return written - before

        for field, query in query_plan:
            query_limit = min(target_per_query, limit - written)
            if query_limit <= 0:
                break
            _progress(f"{source}: query='{query}' field='{field}' target={query_limit} total={written}/{limit}")
            before = written
            try:
                write_items(field, query, query_limit, fetch_query)
            except HarvestError as exc:
                _progress(f"{source}: query='{query}' skipped after error: {exc}")
            _progress(f"{source}: query='{query}' wrote={written - before} total={written}/{limit}")
            if written >= limit:
                break
        for field, query in backfill_plan:
            if written >= limit:
                break
            query_limit = min(limit, max(limit - written, backfill_min_query_limit))
            backfill_fetch = backfill_fetch_query or fetch_query
            _progress(f"{source}: backfill query='{query}' field='{field}' target={query_limit} total={written}/{limit}")
            before = written
            try:
                write_items(field, query, query_limit, backfill_fetch)
            except HarvestError as exc:
                _progress(f"{source}: backfill query='{query}' skipped after error: {exc}")
            _progress(f"{source}: backfill query='{query}' wrote={written - before} total={written}/{limit}")

    if written >= existing_records:
        temp_output.replace(output)
        _progress(f"{source}: done records={written} output={output}")
        return written

    temp_output.unlink(missing_ok=True)
    _progress(
        f"{source}: kept existing output records={existing_records}; "
        f"new records={written} was lower output={output}"
    )
    return existing_records


def _arxiv_search_query(query: str, year: int | None = None) -> str:
    search_query = f'all:"{query}"'
    if year is not None:
        search_query = f"{search_query} AND submittedDate:[{year}01010000 TO {year}12312359]"
    return search_query


def _arxiv_fetch(_field: str, query: str, query_limit: int, year: int | None = None) -> list[dict[str, Any]]:
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    items: list[dict[str, Any]] = []
    for start in range(0, query_limit, ARXIV_BATCH_SIZE):
        batch_size = min(ARXIV_BATCH_SIZE, query_limit - start)
        year_label = f" year={year}" if year is not None else ""
        _progress(f"arxiv: fetch{year_label} query='{query}' start={start} batch={batch_size}")
        try:
            root = _request_xml(
                ARXIV_URL,
                {
                    "search_query": _arxiv_search_query(query, year=year),
                    "start": start,
                    "max_results": batch_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                timeout=90,
            )
        except HarvestError as exc:
            if items:
                _progress(f"arxiv: partial query='{query}' stopped after error: {exc}")
                break
            raise
        entries = root.findall("atom:entry", ns)
        if not entries:
            break
        for entry in entries:
            entry_id = _text(entry.find("atom:id", ns))
            raw = {
                "id": entry_id,
                "title": _text(entry.find("atom:title", ns)),
                "summary": _text(entry.find("atom:summary", ns)),
                "authors": [_text(author.find("atom:name", ns)) for author in entry.findall("atom:author", ns)],
                "published": _text(entry.find("atom:published", ns)),
                "updated": _text(entry.find("atom:updated", ns)),
                "categories": [category.attrib.get("term", "") for category in entry.findall("atom:category", ns)],
                "doi": _text(entry.find("arxiv:doi", ns)),
                "source_id": entry_id,
            }
            if year is not None and _year_from_text(raw["published"] or raw["updated"]) != year:
                continue
            items.append({"source_id": entry_id, "raw": raw})
        time.sleep(ARXIV_SLEEP_SECONDS)
    return items


def harvest_arxiv(*, output_path: str | Path, limit: int) -> int:
    return _write_wrappers(output_path=output_path, source="arxiv", limit=limit, fetch_query=_arxiv_fetch)


def harvest_arxiv_year(*, output_path: str | Path, limit: int, year: int) -> int:
    def fetch_query(field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
        return _arxiv_fetch(field, query, query_limit, year=year)

    return _write_wrappers(output_path=output_path, source="arxiv", limit=limit, fetch_query=fetch_query)


def _ncbi_base_params() -> dict[str, str]:
    params = {"retmode": "json", "tool": "SciScope"}
    if email := os.getenv("NCBI_EMAIL"):
        params["email"] = email
    if api_key := os.getenv("NCBI_API_KEY"):
        params["api_key"] = api_key
    return params


def _year_query(query: str, year: int) -> str:
    return f"({query}) AND {year}[pdat]"


def _ncbi_search_ids(db: str, query: str, query_limit: int, year: int | None = None) -> list[str]:
    term = _year_query(query, year) if year is not None else query
    params = {
        **_ncbi_base_params(),
        "db": db,
        "term": term,
        "retmax": query_limit,
        "sort": "pub+date",
    }
    payload = _request_json(NCBI_ESEARCH_URL, params)
    time.sleep(0.35)
    return list((payload.get("esearchresult") or {}).get("idlist") or [])


def _pubmed_fetch(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
    ids = _ncbi_search_ids("pubmed", query, query_limit)
    return _pubmed_fetch_ids(query=query, ids=ids)


def _pubmed_fetch_ids(*, query: str, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    items: list[dict[str, Any]] = []
    for batch in _batched(ids, NCBI_EFETCH_BATCH_SIZE):
        _progress(f"pubmed: efetch query='{query}' batch={len(batch)}")
        root = _request_xml(
            NCBI_EFETCH_URL,
            {**_ncbi_base_params(), "retmode": "xml", "db": "pubmed", "id": ",".join(batch)},
            timeout=90,
        )
        for article in root.findall(".//PubmedArticle"):
            pmid = _first_text(article, [".//PMID"])
            authors: list[str] = []
            for author in article.findall(".//AuthorList/Author"):
                collective = _first_text(author, ["CollectiveName"])
                name = collective or " ".join(
                    part for part in [_first_text(author, ["ForeName"]), _first_text(author, ["LastName"])] if part
                )
                if name:
                    authors.append(name)
            raw = {
                "pmid": pmid,
                "title": _first_text(article, [".//ArticleTitle"]),
                "abstract": " ".join(_text(node) for node in article.findall(".//Abstract/AbstractText")),
                "authors": authors,
                "year": _first_text(article, [".//PubDate/Year", ".//ArticleDate/Year"]),
                "keywords": [_text(node) for node in article.findall(".//KeywordList/Keyword")],
                "journal": _first_text(article, [".//Journal/Title"]),
                "doi": _first_text(article, [".//ArticleId[@IdType='doi']"]),
            }
            items.append({"source_id": pmid, "raw": raw})
        time.sleep(0.35)
    return items


def harvest_pubmed(*, output_path: str | Path, limit: int) -> int:
    return _write_wrappers(output_path=output_path, source="pubmed", limit=limit, fetch_query=_pubmed_fetch)


def harvest_pubmed_year(*, output_path: str | Path, limit: int, year: int) -> int:
    def fetch_query(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
        ids = _ncbi_search_ids("pubmed", query, query_limit, year=year)
        return [
            item
            for item in _pubmed_fetch_ids(query=query, ids=ids)
            if _year_from_text((item.get("raw") or {}).get("year")) == year
        ]

    return _write_wrappers(output_path=output_path, source="pubmed", limit=limit, fetch_query=fetch_query)


def _pmc_fetch(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
    ids = _ncbi_search_ids("pmc", query, query_limit)
    if not ids:
        return []
    items: list[dict[str, Any]] = []
    parsed_ids: set[str] = set()
    for batch in _batched(ids, NCBI_EFETCH_BATCH_SIZE):
        _progress(f"pmc: efetch query='{query}' batch={len(batch)}")
        root = _request_xml(
            NCBI_EFETCH_URL,
            {**_ncbi_base_params(), "retmode": "xml", "db": "pmc", "id": ",".join(batch)},
            timeout=120,
        )
        for index, article in enumerate(root.findall(".//{*}article")):
            pmc_id = _first_text(article, [".//{*}article-id[@pub-id-type='pmc']"])
            source_id = f"PMC{pmc_id}" if pmc_id and not pmc_id.startswith("PMC") else pmc_id
            if not source_id and index < len(batch):
                source_id = f"PMC{batch[index]}"
            parsed_ids.add(source_id)
            paragraphs = [_text(node) for node in article.findall(".//{*}body//{*}p")]
            raw = {
                "pmcid": source_id,
                "title": _first_text(article, [".//{*}article-title"]),
                "abstract": " ".join(_text(node) for node in article.findall(".//{*}abstract")),
                "authors": [
                    " ".join(
                        part
                        for part in [_first_text(author, [".//{*}given-names"]), _first_text(author, [".//{*}surname"])]
                        if part
                    )
                    for author in article.findall(".//{*}contrib[@contrib-type='author']")
                ],
                "year": _first_text(article, [".//{*}pub-date/{*}year"]),
                "keywords": [_text(node) for node in article.findall(".//{*}kwd")],
                "doi": _first_text(article, [".//{*}article-id[@pub-id-type='doi']"]),
                "body_excerpt": " ".join(paragraphs)[:2500],
            }
            items.append({"source_id": source_id, "raw": raw})
        time.sleep(0.35)
    missing_ids = [pmc_id for pmc_id in ids if f"PMC{pmc_id}" not in parsed_ids and pmc_id not in parsed_ids]
    if missing_ids:
        items.extend(_pmc_summary_fetch(missing_ids))
    return items


def pmc_summary_record_to_item(record: dict[str, Any]) -> dict[str, Any]:
    article_ids = record.get("articleids") or []
    identifiers = {
        str(item.get("idtype") or "").lower(): str(item.get("value") or "").strip()
        for item in article_ids
        if isinstance(item, dict)
    }
    pmcid = identifiers.get("pmc") or identifiers.get("pmcid") or f"PMC{record.get('uid') or ''}"
    if pmcid and not pmcid.startswith("PMC"):
        pmcid = f"PMC{pmcid}"
    raw = {
        "pmcid": pmcid,
        "title": record.get("title") or "",
        "abstract": "",
        "authors": [str(author.get("name") or "").strip() for author in record.get("authors") or []],
        "year": re.search(r"(19|20)\d{2}", str(record.get("pubdate") or "")).group(0)
        if re.search(r"(19|20)\d{2}", str(record.get("pubdate") or ""))
        else "",
        "keywords": [record.get("fulljournalname") or ""],
        "journal": record.get("fulljournalname") or "",
        "doi": identifiers.get("doi") or "",
        "body_excerpt": "",
    }
    return {"source_id": pmcid, "raw": raw}


def _pmc_summary_fetch(ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    items: list[dict[str, Any]] = []
    for batch in _batched(ids, NCBI_ESUMMARY_BATCH_SIZE):
        _progress(f"pmc: esummary batch={len(batch)}")
        payload = _request_json(
            NCBI_ESUMMARY_URL,
            {**_ncbi_base_params(), "retmode": "json", "db": "pmc", "id": ",".join(batch)},
            timeout=90,
        )
        result = payload.get("result") or {}
        for uid in result.get("uids") or []:
            record = result.get(uid) or {}
            item = pmc_summary_record_to_item(record)
            if item["source_id"]:
                items.append(item)
        time.sleep(0.35)
    return items


def _pmc_summary_query_fetch(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
    ids = _ncbi_search_ids("pmc", query, query_limit)
    return _pmc_summary_fetch(ids)


def harvest_pmc(*, output_path: str | Path, limit: int) -> int:
    return _write_wrappers(
        output_path=output_path,
        source="pmc",
        limit=limit,
        fetch_query=_pmc_fetch,
        queries=PMC_QUERIES,
        backfill_queries=PMC_BACKFILL_QUERIES,
        backfill_fetch_query=_pmc_summary_query_fetch,
        backfill_min_query_limit=250,
    )


def harvest_pmc_year(*, output_path: str | Path, limit: int, year: int) -> int:
    def fetch_query(field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
        ids = _ncbi_search_ids("pmc", query, query_limit, year=year)
        if not ids:
            return []
        items: list[dict[str, Any]] = []
        parsed_ids: set[str] = set()
        for batch in _batched(ids, NCBI_EFETCH_BATCH_SIZE):
            _progress(f"pmc: efetch year={year} query='{query}' batch={len(batch)}")
            root = _request_xml(
                NCBI_EFETCH_URL,
                {**_ncbi_base_params(), "retmode": "xml", "db": "pmc", "id": ",".join(batch)},
                timeout=120,
            )
            for index, article in enumerate(root.findall(".//{*}article")):
                pmc_id = _first_text(article, [".//{*}article-id[@pub-id-type='pmc']"])
                source_id = f"PMC{pmc_id}" if pmc_id and not pmc_id.startswith("PMC") else pmc_id
                if not source_id and index < len(batch):
                    source_id = f"PMC{batch[index]}"
                parsed_ids.add(source_id)
                paragraphs = [_text(node) for node in article.findall(".//{*}body//{*}p")]
                raw = {
                    "pmcid": source_id,
                    "title": _first_text(article, [".//{*}article-title"]),
                    "abstract": " ".join(_text(node) for node in article.findall(".//{*}abstract")),
                    "authors": [
                        " ".join(
                            part
                            for part in [
                                _first_text(author, [".//{*}given-names"]),
                                _first_text(author, [".//{*}surname"]),
                            ]
                            if part
                        )
                        for author in article.findall(".//{*}contrib[@contrib-type='author']")
                    ],
                    "year": _first_text(article, [".//{*}pub-date/{*}year"]) or str(year),
                    "keywords": [_text(node) for node in article.findall(".//{*}kwd")],
                    "doi": _first_text(article, [".//{*}article-id[@pub-id-type='doi']"]),
                    "body_excerpt": " ".join(paragraphs)[:2500],
                }
                if _year_from_text(raw["year"]) != year:
                    continue
                items.append({"source_id": source_id, "raw": raw})
            time.sleep(0.35)
        missing_ids = [pmc_id for pmc_id in ids if f"PMC{pmc_id}" not in parsed_ids and pmc_id not in parsed_ids]
        if missing_ids:
            items.extend(_pmc_summary_fetch(missing_ids))
        return items

    def summary_query(field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
        return _pmc_summary_fetch(_ncbi_search_ids("pmc", query, query_limit, year=year))

    return _write_wrappers(
        output_path=output_path,
        source="pmc",
        limit=limit,
        fetch_query=fetch_query,
        queries=PMC_QUERIES,
        backfill_queries=PMC_BACKFILL_QUERIES,
        backfill_fetch_query=summary_query,
        backfill_min_query_limit=250,
    )


def _crossref_fetch(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
    headers = {}
    if email := os.getenv("CROSSREF_EMAIL"):
        headers["User-Agent"] = f"SciScopeHarvester/0.1 (mailto:{email})"
    items: list[dict[str, Any]] = []
    for offset in range(0, query_limit, CROSSREF_BATCH_SIZE):
        rows = min(CROSSREF_BATCH_SIZE, query_limit - offset)
        _progress(f"crossref: fetch query='{query}' offset={offset} rows={rows}")
        payload = _request_json(
            CROSSREF_URL,
            {
                "query": query,
                "rows": rows,
                "offset": offset,
                "sort": "published",
                "order": "desc",
                "filter": "from-pub-date:2020-01-01,type:journal-article",
            },
            headers=headers,
            timeout=90,
        )
        batch = (payload.get("message") or {}).get("items") or []
        if not batch:
            break
        for work in batch:
            doi = str(work.get("DOI") or "").strip()
            if doi:
                items.append({"source_id": doi, "raw": work})
        if len(batch) < rows:
            break
        time.sleep(1.0)
    return items


def harvest_crossref(*, output_path: str | Path, limit: int) -> int:
    return _write_wrappers(output_path=output_path, source="crossref", limit=limit, fetch_query=_crossref_fetch)


def harvest_crossref_year(*, output_path: str | Path, limit: int, year: int) -> int:
    def fetch_query(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
        headers = {}
        if email := os.getenv("CROSSREF_EMAIL"):
            headers["User-Agent"] = f"SciScopeHarvester/0.1 (mailto:{email})"
        items: list[dict[str, Any]] = []
        for offset in range(0, query_limit, CROSSREF_BATCH_SIZE):
            rows = min(CROSSREF_BATCH_SIZE, query_limit - offset)
            _progress(f"crossref: fetch year={year} query='{query}' offset={offset} rows={rows}")
            payload = _request_json(
                CROSSREF_URL,
                {
                    "query": query,
                    "rows": rows,
                    "offset": offset,
                    "sort": "published",
                    "order": "desc",
                    "filter": f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31,type:journal-article",
                },
                headers=headers,
                timeout=90,
            )
            batch = (payload.get("message") or {}).get("items") or []
            if not batch:
                break
            for work in batch:
                doi = str(work.get("DOI") or "").strip()
                if doi:
                    items.append({"source_id": doi, "raw": work})
            if len(batch) < rows:
                break
            time.sleep(1.0)
        return items

    return _write_wrappers(output_path=output_path, source="crossref", limit=limit, fetch_query=fetch_query)


def _semantic_scholar_fetch(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
    headers = {}
    if api_key := os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = api_key
    payload = _request_json(
        SEMANTIC_SCHOLAR_URL,
        {
            "query": query,
            "limit": min(query_limit, 100),
            "fields": "paperId,title,abstract,authors,year,fieldsOfStudy,s2FieldsOfStudy,citationCount,url,publicationTypes,venue",
        },
        headers=headers,
    )
    items = [{"source_id": str(paper.get("paperId") or ""), "raw": paper} for paper in payload.get("data") or []]
    time.sleep(1.5)
    return items


def harvest_semantic_scholar(*, output_path: str | Path, limit: int) -> int:
    return _write_wrappers(
        output_path=output_path,
        source="semantic_scholar",
        limit=limit,
        fetch_query=_semantic_scholar_fetch,
    )


def _doaj_fetch(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
    query_limit = min(query_limit, DOAJ_QUERY_RESULT_CAP)
    page_size = min(query_limit, DOAJ_BATCH_SIZE)
    url = f"{DOAJ_URL}/{quote(query)}"
    items: list[dict[str, Any]] = []
    page = 1
    while len(items) < query_limit:
        _progress(f"doaj: fetch query='{query}' page={page} page_size={page_size}")
        payload = _request_json(url, {"page": page, "pageSize": min(page_size, query_limit - len(items))}, timeout=90)
        results = payload.get("results") or []
        if not results:
            break
        items.extend(
            {
                "source_id": str(article.get("id") or article.get("bibjson", {}).get("identifier", [{}])[0].get("id") or ""),
                "raw": article,
            }
            for article in results
        )
        if len(results) < page_size:
            break
        page += 1
        time.sleep(0.5)
    return items


def harvest_doaj(*, output_path: str | Path, limit: int) -> int:
    return _write_wrappers(output_path=output_path, source="doaj", limit=limit, fetch_query=_doaj_fetch)


def _doaj_article_year(article: dict[str, Any]) -> int | None:
    bibjson = article.get("bibjson") or {}
    value = bibjson.get("year") or bibjson.get("publication_year") or bibjson.get("month")
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _doaj_fetch_year(_field: str, query: str, query_limit: int, year: int) -> list[dict[str, Any]]:
    query_limit = min(query_limit, DOAJ_QUERY_RESULT_CAP)
    page_size = min(query_limit, DOAJ_BATCH_SIZE)
    server_query = f"{query} AND bibjson.year:{year}"
    url = f"{DOAJ_URL}/{quote(server_query)}"
    items: list[dict[str, Any]] = []
    page = 1
    while len(items) < query_limit:
        _progress(f"doaj: fetch year={year} query='{query}' page={page} page_size={page_size}")
        try:
            payload = _request_json(
                url,
                {"page": page, "pageSize": min(page_size, query_limit - len(items))},
                timeout=90,
            )
        except HarvestError as exc:
            if items:
                _progress(f"doaj: partial year={year} query='{query}' stopped after error: {exc}")
                break
            raise
        results = payload.get("results") or []
        if not results:
            break
        for article in results:
            if _doaj_article_year(article) != year:
                continue
            source_id = str(article.get("id") or article.get("bibjson", {}).get("identifier", [{}])[0].get("id") or "")
            if source_id:
                items.append({"source_id": source_id, "raw": article})
            if len(items) >= query_limit:
                break
        if len(results) < page_size:
            break
        page += 1
        time.sleep(0.5)
    return items


def harvest_doaj_year(*, output_path: str | Path, limit: int, year: int) -> int:
    def fetch_query(field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
        return _doaj_fetch_year(field, query, query_limit, year=year)

    return _write_wrappers(output_path=output_path, source="doaj", limit=limit, fetch_query=fetch_query)


def _core_fetch(_field: str, query: str, query_limit: int) -> list[dict[str, Any]]:
    api_key = os.getenv("CORE_API_KEY")
    if not api_key:
        raise HarvestError("CORE_API_KEY is required for CORE harvesting")
    payload = _request_json(
        CORE_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps({"q": query, "limit": query_limit, "offset": 0}).encode("utf-8"),
    )
    results = payload.get("results") or []
    return [{"source_id": str(work.get("id") or ""), "raw": work} for work in results]


def harvest_core(*, output_path: str | Path, limit: int) -> int:
    return _write_wrappers(output_path=output_path, source="core", limit=limit, fetch_query=_core_fetch)


HARVESTERS: dict[str, Callable[..., int]] = {
    "openalex": harvest_openalex,
    "arxiv": harvest_arxiv,
    "pubmed": harvest_pubmed,
    "pmc": harvest_pmc,
    "crossref": harvest_crossref,
    "semantic_scholar": harvest_semantic_scholar,
    "doaj": harvest_doaj,
    "core": harvest_core,
}


def harvest_source(*, source: str, output_path: str | Path, limit: int) -> int:
    if source not in HARVESTERS:
        raise HarvestError(f"Unsupported source: {source}. Supported sources: {', '.join(SUPPORTED_SOURCES)}")
    return HARVESTERS[source](output_path=output_path, limit=limit)


YEAR_HARVESTERS: dict[str, Callable[..., int]] = {
    "openalex": harvest_openalex,
    "arxiv": harvest_arxiv_year,
    "pubmed": harvest_pubmed_year,
    "pmc": harvest_pmc_year,
    "crossref": harvest_crossref_year,
    "doaj": harvest_doaj_year,
}

YEAR_SUPPORTED_SOURCES = tuple(YEAR_HARVESTERS)


def harvest_source_year(*, source: str, output_path: str | Path, limit: int, year: int) -> int:
    if source not in YEAR_HARVESTERS:
        raise HarvestError(
            f"Unsupported year-balanced source: {source}. Supported sources: {', '.join(YEAR_SUPPORTED_SOURCES)}"
        )
    return YEAR_HARVESTERS[source](output_path=output_path, limit=limit, year=year)


def strip_markup(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()
