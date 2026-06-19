from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OPENALEX_WORKS_URL = "https://api.openalex.org/works"

DEFAULT_QUERIES = [
    ("computer science", "large language model"),
    ("computer science", "retrieval augmented generation"),
    ("computer science", "knowledge graph"),
    ("computer science", "graph neural network"),
    ("biomedicine", "drug discovery"),
    ("biomedicine", "biomedical natural language processing"),
    ("biomedicine", "protein design"),
    ("materials science", "materials discovery"),
    ("materials science", "battery materials"),
    ("materials science", "catalyst discovery"),
]


class OpenAlexError(RuntimeError):
    """Raised when OpenAlex harvesting fails."""


def _progress(message: str) -> None:
    print(f"[harvest] openalex: {message}", file=sys.stderr, flush=True)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _request_json(params: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    query = urlencode({key: value for key, value in params.items() if value not in {None, ""}})
    request = Request(
        f"{OPENALEX_WORKS_URL}?{query}",
        headers={"User-Agent": "SciScopeHarvester/0.1"},
    )
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = OpenAlexError(f"OpenAlex HTTP {exc.code}: {body[:400]}")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise last_error from exc
            time.sleep(float(exc.headers.get("Retry-After") or attempt * 5))
        except (URLError, IncompleteRead, RemoteDisconnected) as exc:
            last_error = OpenAlexError(f"OpenAlex request failed: {exc}")
            if attempt == 3:
                raise last_error from exc
            time.sleep(attempt * 2)
    raise OpenAlexError(f"OpenAlex request failed: {last_error}")


def _query_params(query: str, cursor: str, per_page: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "search": query,
        "filter": "has_abstract:true",
        "per-page": per_page,
        "cursor": cursor,
        "select": ",".join(
            [
                "id",
                "doi",
                "display_name",
                "title",
                "publication_year",
                "publication_date",
                "authorships",
                "abstract_inverted_index",
                "concepts",
                "keywords",
                "primary_topic",
                "topics",
                "cited_by_count",
                "ids",
            ]
        ),
    }
    if email := os.getenv("OPENALEX_EMAIL"):
        params["mailto"] = email
    if api_key := os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = api_key
    return params


def harvest_openalex(
    *,
    output_path: str | Path,
    limit: int,
    queries: list[tuple[str, str]] | None = None,
    per_page: int = 200,
    delay_seconds: float = 0.2,
) -> int:
    """Harvest OpenAlex works into JSONL while preserving raw payloads."""

    if limit <= 0:
        raise ValueError("limit must be positive")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    query_plan = queries or DEFAULT_QUERIES
    target_per_query = max(1, (limit + len(query_plan) - 1) // len(query_plan))

    seen_ids: set[str] = set()
    written = 0
    _progress(f"start limit={limit} output={output}")
    with output.open("w", encoding="utf-8") as handle:
        for field, query in query_plan:
            cursor = "*"
            query_written = 0
            _progress(f"query='{query}' field='{field}' target={target_per_query} total={written}/{limit}")
            while written < limit and query_written < target_per_query:
                page_size = min(per_page, limit - written, target_per_query - query_written)
                payload = _request_json(_query_params(query=query, cursor=cursor, per_page=page_size))
                before = written
                for work in payload.get("results", []):
                    source_id = str(work.get("id") or "")
                    if not source_id or source_id in seen_ids:
                        continue
                    seen_ids.add(source_id)
                    record = {
                        "source": "openalex",
                        "source_id": source_id,
                        "query": query,
                        "field_seed": field,
                        "crawled_at": _utc_now(),
                        "raw": work,
                    }
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1
                    query_written += 1
                    if written >= limit or query_written >= target_per_query:
                        break
                _progress(
                    f"query='{query}' page_wrote={written - before} "
                    f"query_total={query_written}/{target_per_query} total={written}/{limit}"
                )

                next_cursor = payload.get("meta", {}).get("next_cursor")
                if not next_cursor or next_cursor == cursor or not payload.get("results"):
                    break
                cursor = next_cursor
                time.sleep(delay_seconds)
            _progress(f"query='{query}' done wrote={query_written} total={written}/{limit}")

            if written >= limit:
                break

    _progress(f"done records={written} output={output}")
    return written
