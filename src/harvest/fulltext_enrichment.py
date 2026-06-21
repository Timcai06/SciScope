from __future__ import annotations

import argparse
import gzip
import html
import io
import json
import os
import re
import subprocess
import tarfile
import time
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ARXIV_EPRINT_URL = "https://arxiv.org/e-print/{paper_id}"
PMC_FULLTEXT_URL = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
DEFAULT_TEXT_LIMIT = 12_000
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_DOWNLOAD_BYTES = 4_000_000
DEFAULT_BROWSER_TIMEOUT_SECONDS = 30
MIN_BROWSER_FULLTEXT_WORDS = 700
SUPPORTED_SOURCES = ("arxiv", "crossref", "doaj", "openalex", "pubmed")
BROWSER_FALLBACK_DOMAINS = (
    "mdpi.com",
    "link.springer.com",
    "frontiersin.org",
    "peerj.com",
    "jmir.org",
)
STABLE_FULLTEXT_DOMAINS = (
    "mdpi.com",
    "link.springer.com",
    "frontiersin.org",
    "peerj.com",
    "jmir.org",
    "copernicus.org",
    "europepmc.org",
    "ncbi.nlm.nih.gov",
    "arxiv.org",
)
BAD_BROWSER_TEXT_MARKERS = (
    "performing security verification",
    "verify that you're not a robot",
    "enable javascript and then reload the page",
    "access denied",
)


@dataclass
class EnrichmentSummary:
    source: str
    files: int
    records_seen: int
    records_with_full_text_before: int
    records_enriched: int
    records_with_full_text_after: int
    errors: int


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def _write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temp_path.replace(path)


def _has_full_text(wrapper: dict[str, Any]) -> bool:
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    return bool(
        str(raw.get("body_excerpt") or raw.get("fullText") or raw.get("full_text") or "").strip()
    )


def _matches_field_filter(wrapper: dict[str, Any], field_filter: str | None) -> bool:
    if not field_filter:
        return True
    needle = field_filter.strip().lower()
    if not needle:
        return True
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    haystack = " ".join(
        str(value or "")
        for value in (
            wrapper.get("field_seed"),
            wrapper.get("query"),
            raw.get("field"),
            raw.get("category"),
        )
    ).lower()
    return needle in haystack


def _has_failed_fulltext_attempt(wrapper: dict[str, Any], source: str) -> bool:
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    return (
        str(raw.get("full_text_attempt_source") or "") == source
        and str(raw.get("full_text_attempt_status") or "") in {"failed", "no_fulltext"}
    )


def _mark_fulltext_attempt(wrapper: dict[str, Any], *, source: str, status: str, reason: str) -> dict[str, Any]:
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    return {
        **wrapper,
        "raw": {
            **raw,
            "full_text_attempt_source": source,
            "full_text_attempt_status": status,
            "full_text_attempt_reason": reason,
            "full_text_attempted_at": _utc_now(),
        },
    }


def _arxiv_id(wrapper: dict[str, Any]) -> str:
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    value = str(raw.get("id") or raw.get("source_id") or wrapper.get("source_id") or "").strip()
    value = value.rstrip("/").rsplit("/", 1)[-1]
    value = re.sub(r"v\d+$", "", value)
    return value


def _progress(message: str) -> None:
    print(f"[fulltext] {message}", file=sys.stderr, flush=True)


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _fetch_bytes(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
) -> bytes:
    request = Request(url, headers=_request_headers())
    with urlopen(request, timeout=timeout) as response:
        chunks: list[bytes] = []
        total = 0
        started_at = time.monotonic()
        while True:
            if time.monotonic() - started_at > timeout:
                raise TimeoutError(f"download exceeded timeout={timeout}s")
            chunk = response.read(min(64 * 1024, max_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise OSError(f"download exceeded max_bytes={max_bytes}")
        return b"".join(chunks)


def _strip_latex(text: str) -> str:
    text = re.sub(r"%.*", " ", text)
    text = re.sub(r"\\begin\{(figure|table|equation|align|tikzpicture).*?\\end\{\1\}", " ", text, flags=re.S)
    text = re.sub(r"\\(section|subsection|subsubsection|paragraph)\*?\{([^{}]+)\}", r"\2. ", text)
    text = re.sub(r"\\(title|caption|label|ref|cite|author|date)\*?(\[[^\]]*\])?\{[^{}]*\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", " ", text)
    text = re.sub(r"[{}$^_&#]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _text_from_arxiv_payload(payload: bytes) -> str:
    candidates: list[str] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
            for member in archive.getmembers():
                name = member.name.lower()
                if not member.isfile() or not name.endswith((".tex", ".txt")):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                candidates.append(extracted.read().decode("utf-8", errors="ignore"))
    except tarfile.TarError:
        pass

    if not candidates:
        try:
            candidates.append(gzip.decompress(payload).decode("utf-8", errors="ignore"))
        except (OSError, EOFError):
            candidates.append(payload.decode("utf-8", errors="ignore"))

    cleaned = [_strip_latex(text) for text in candidates]
    cleaned = [text for text in cleaned if len(text.split()) >= 80]
    if not cleaned:
        return ""
    return max(cleaned, key=len)


def _clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _text_from_html(payload: bytes) -> str:
    markup = payload.decode("utf-8", errors="ignore")
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(markup, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        container = soup.find("article") or soup.find("main") or soup.body or soup
        return _clean_text(container.get_text(" "))
    except Exception:
        markup = re.sub(r"(?is)<(script|style).*?</\1>", " ", markup)
        markup = re.sub(r"(?s)<[^>]+>", " ", markup)
        return _clean_text(markup)


def _text_from_pdf(payload: bytes) -> str:
    try:
        import fitz

        with fitz.open(stream=payload, filetype="pdf") as document:
            pages = [page.get_text("text") for page in document]
        return _clean_text(" ".join(pages))
    except Exception:
        return ""


def _text_from_url_payload(payload: bytes, url: str) -> str:
    if payload.startswith(b"%PDF") or url.lower().split("?", 1)[0].endswith(".pdf"):
        return _text_from_pdf(payload)
    if b"<html" in payload[:2000].lower() or b"<body" in payload[:2000].lower():
        return _text_from_html(payload)
    return _clean_text(payload.decode("utf-8", errors="ignore"))


def _should_try_browser(url: str) -> bool:
    lowered = url.lower()
    return any(domain in lowered for domain in BROWSER_FALLBACK_DOMAINS)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_doi_url(url: str) -> bool:
    return _host(url) in {"doi.org", "dx.doi.org"}


def _is_stable_fulltext_url(url: str) -> bool:
    host = _host(url)
    return any(host == domain or host.endswith(f".{domain}") for domain in STABLE_FULLTEXT_DOMAINS)


def _resolve_redirect_url(url: str, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = Request(url, headers=_request_headers())
    with urlopen(request, timeout=timeout_seconds) as response:
        return str(response.geturl() or url)


def _browser_fetch_script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "fetch_fulltext_browser.cjs"


def _fetch_text_with_browser(
    url: str,
    *,
    timeout_seconds: int = DEFAULT_BROWSER_TIMEOUT_SECONDS,
) -> str:
    script = _browser_fetch_script()
    if not script.exists():
        return ""
    env = {**os.environ, "SCISCOPE_BROWSER_TIMEOUT_MS": str(int(timeout_seconds * 1000))}
    try:
        completed = subprocess.run(
            ["node", str(script), url],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ""
    text = _clean_text(str(payload.get("text") or ""))
    lowered = text.lower()
    if any(marker in lowered for marker in BAD_BROWSER_TEXT_MARKERS):
        return ""
    if len(text.split()) < MIN_BROWSER_FULLTEXT_WORDS:
        return ""
    return text


def _doi_url(value: Any) -> str:
    doi = str(value or "").strip()
    if not doi:
        return ""
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = doi.strip()
    return f"https://doi.org/{doi}" if doi else ""


def _pmcid_url(value: Any) -> str:
    pmcid = str(value or "").strip()
    if not pmcid:
        return ""
    if pmcid.isdigit():
        pmcid = f"PMC{pmcid}"
    if not pmcid.upper().startswith("PMC"):
        pmcid = f"PMC{pmcid}"
    return PMC_FULLTEXT_URL.format(pmcid=pmcid)


def _dedupe_urls(urls: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for url, reason in urls:
        normalized = str(url or "").strip()
        if not normalized or not normalized.startswith(("http://", "https://")):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append((normalized, reason))
    return result


def _crossref_candidate_urls(raw: dict[str, Any]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for link in raw.get("link") or []:
        if not isinstance(link, dict):
            continue
        url = link.get("URL") or link.get("url")
        app = str(link.get("intended-application") or "").lower()
        content_type = str(link.get("content-type") or link.get("content_type") or "").lower()
        if url and ("text-mining" in app or "pdf" in content_type or "html" in content_type):
            urls.append((str(url), "crossref_fulltext_url"))
    primary = (raw.get("resource") or {}).get("primary") if isinstance(raw.get("resource"), dict) else {}
    if isinstance(primary, dict):
        urls.append((str(primary.get("URL") or primary.get("url") or ""), "crossref_primary_url"))
    urls.append((_doi_url(raw.get("DOI") or raw.get("doi") or raw.get("URL")), "crossref_doi_url"))
    return _dedupe_urls(urls)


def _doaj_candidate_urls(raw: dict[str, Any]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    bibjson = raw.get("bibjson") if isinstance(raw.get("bibjson"), dict) else {}
    for link in bibjson.get("link") or []:
        if not isinstance(link, dict):
            continue
        if str(link.get("type") or "").lower() == "fulltext":
            urls.append((str(link.get("url") or link.get("URL") or ""), "doaj_fulltext_url"))
    for identifier in bibjson.get("identifier") or []:
        if isinstance(identifier, dict) and str(identifier.get("type") or "").lower() == "doi":
            urls.append((_doi_url(identifier.get("id")), "doaj_doi_url"))
    return _dedupe_urls(urls)


def _openalex_candidate_urls(raw: dict[str, Any]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for location_key in ("primary_location", "best_oa_location"):
        location = raw.get(location_key)
        if isinstance(location, dict):
            urls.append((str(location.get("pdf_url") or ""), "openalex_pdf_url"))
            urls.append((str(location.get("landing_page_url") or ""), "openalex_landing_page_url"))
    open_access = raw.get("open_access")
    if isinstance(open_access, dict):
        urls.append((str(open_access.get("oa_url") or ""), "openalex_oa_url"))
    ids = raw.get("ids") if isinstance(raw.get("ids"), dict) else {}
    urls.append((_doi_url(raw.get("doi") or ids.get("doi")), "openalex_doi_url"))
    return _dedupe_urls(urls)


def _pubmed_candidate_urls(raw: dict[str, Any]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for key in ("pmcid", "pmc"):
        if raw.get(key):
            urls.append((_pmcid_url(raw.get(key)), "pubmed_pmc_url"))
    urls.append((_doi_url(raw.get("doi")), "pubmed_doi_url"))
    return _dedupe_urls(urls)


def _candidate_urls(wrapper: dict[str, Any], source: str) -> list[tuple[str, str]]:
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    if source == "crossref":
        return _crossref_candidate_urls(raw)
    if source == "doaj":
        return _doaj_candidate_urls(raw)
    if source == "openalex":
        return _openalex_candidate_urls(raw)
    if source == "pubmed":
        return _pubmed_candidate_urls(raw)
    return []


def _enrich_url_record(
    wrapper: dict[str, Any],
    *,
    source: str,
    text_limit: int,
    timeout_seconds: int,
    max_download_bytes: int,
    browser_fallback: bool = True,
    stable_only: bool = False,
) -> tuple[dict[str, Any], bool]:
    if _has_full_text(wrapper):
        return wrapper, False
    for url, reason in _candidate_urls(wrapper, source):
        fetch_url = url
        if stable_only and not _is_stable_fulltext_url(url):
            if not _is_doi_url(url):
                continue
            try:
                fetch_url = _resolve_redirect_url(url, timeout_seconds=timeout_seconds)
            except (HTTPError, URLError, TimeoutError, OSError):
                continue
            if not _is_stable_fulltext_url(fetch_url):
                continue
        text = ""
        source_reason = reason
        try:
            payload = _fetch_bytes(fetch_url, timeout=timeout_seconds, max_bytes=max_download_bytes)
            text = _text_from_url_payload(payload, fetch_url)
        except (HTTPError, URLError, TimeoutError, OSError):
            if browser_fallback and _should_try_browser(fetch_url):
                text = _fetch_text_with_browser(fetch_url, timeout_seconds=max(timeout_seconds, DEFAULT_BROWSER_TIMEOUT_SECONDS))
                source_reason = f"{reason}_browser"
            else:
                continue
        if len(text.split()) < 80:
            if browser_fallback and source_reason == reason and _should_try_browser(fetch_url):
                browser_text = _fetch_text_with_browser(
                    fetch_url,
                    timeout_seconds=max(timeout_seconds, DEFAULT_BROWSER_TIMEOUT_SECONDS),
                )
                if len(browser_text.split()) >= 80:
                    text = browser_text
                    source_reason = f"{reason}_browser"
                else:
                    continue
            else:
                continue
        if not text:
            continue
        raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
        enriched = {
            **wrapper,
            "raw": {
                **raw,
                "body_excerpt": text[:text_limit],
                "fullText": text[:text_limit],
                "full_text_source": source_reason,
                "full_text_url": fetch_url,
                "full_text_enriched_at": _utc_now(),
            },
        }
        return enriched, True
    return wrapper, False


def _enrich_arxiv_record(
    wrapper: dict[str, Any],
    *,
    text_limit: int,
    timeout_seconds: int,
    max_download_bytes: int,
) -> tuple[dict[str, Any], bool]:
    if _has_full_text(wrapper):
        return wrapper, False
    paper_id = _arxiv_id(wrapper)
    if not paper_id:
        return wrapper, False
    url = ARXIV_EPRINT_URL.format(paper_id=paper_id)
    payload = _fetch_bytes(url, timeout=timeout_seconds, max_bytes=max_download_bytes)
    text = _text_from_arxiv_payload(payload)
    if not text:
        return wrapper, False
    raw = wrapper.get("raw") if isinstance(wrapper.get("raw"), dict) else {}
    enriched = {
        **wrapper,
        "raw": {
            **raw,
            "body_excerpt": text[:text_limit],
            "fullText": text[:text_limit],
            "full_text_source": "arxiv_eprint",
            "full_text_url": url,
            "full_text_enriched_at": _utc_now(),
        },
    }
    return enriched, True


def enrich_fulltext_in_place(
    *,
    canonical_dir: str | Path = "data/raw_canonical",
    source: str = "arxiv",
    years: list[str] | None = None,
    limit: int | None = None,
    sleep_seconds: float = 3.0,
    text_limit: int = DEFAULT_TEXT_LIMIT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    max_attempts: int | None = None,
    checkpoint_every: int = 25,
    browser_fallback: bool = True,
    stable_only: bool = False,
    field_filter: str | None = None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"Unsupported source for in-place full-text enrichment: {source}")

    source_dir = Path(canonical_dir) / source
    target_years = years or ["2022", "2023", "2024", "2025", "2026"]
    paths = [source_dir / f"{year}.jsonl" for year in target_years if (source_dir / f"{year}.jsonl").exists()]

    summary = EnrichmentSummary(
        source=source,
        files=0,
        records_seen=0,
        records_with_full_text_before=0,
        records_enriched=0,
        records_with_full_text_after=0,
        errors=0,
    )

    remaining = limit
    remaining_attempts = max_attempts
    for path in paths:
        records = _read_jsonl(path)
        changed = False
        changed_since_checkpoint = 0
        summary.files += 1
        for index, record in enumerate(records):
            if remaining is not None and remaining <= 0:
                break
            if remaining_attempts is not None and remaining_attempts <= 0:
                break
            if not _matches_field_filter(record, field_filter):
                continue
            summary.records_seen += 1
            had_full_text = _has_full_text(record)
            summary.records_with_full_text_before += int(had_full_text)
            if had_full_text:
                summary.records_with_full_text_after += 1
                continue
            if not retry_failed and _has_failed_fulltext_attempt(record, source):
                continue
            if remaining_attempts is not None:
                remaining_attempts -= 1
            did_enrich = False
            try:
                if source == "arxiv":
                    paper_id = _arxiv_id(record)
                    _progress(f"{path.name}: fetch arxiv_id={paper_id} seen={summary.records_seen} enriched={summary.records_enriched}")
                    enriched, did_enrich = _enrich_arxiv_record(
                        record,
                        text_limit=text_limit,
                        timeout_seconds=timeout_seconds,
                        max_download_bytes=max_download_bytes,
                    )
                else:
                    _progress(f"{path.name}: fetch source={source} seen={summary.records_seen} enriched={summary.records_enriched}")
                    enriched, did_enrich = _enrich_url_record(
                        record,
                        source=source,
                        text_limit=text_limit,
                        timeout_seconds=timeout_seconds,
                        max_download_bytes=max_download_bytes,
                        browser_fallback=browser_fallback,
                        stable_only=stable_only,
                    )
            except (HTTPError, URLError, TimeoutError, OSError):
                records[index] = _mark_fulltext_attempt(record, source=source, status="failed", reason="fetch_error")
                changed = True
                changed_since_checkpoint += 1
                summary.errors += 1
                _progress(f"{path.name}: failed seen={summary.records_seen} errors={summary.errors}")
                if checkpoint_every > 0 and changed_since_checkpoint >= checkpoint_every:
                    _write_jsonl_atomic(path, records)
                    changed_since_checkpoint = 0
                    _progress(f"{path.name}: checkpoint enriched={summary.records_enriched}")
                continue
            if did_enrich:
                records[index] = enriched
                changed = True
                changed_since_checkpoint += 1
                summary.records_enriched += 1
                summary.records_with_full_text_after += 1
                if remaining is not None:
                    remaining -= 1
                _progress(f"{path.name}: enriched total={summary.records_enriched}")
                if checkpoint_every > 0 and changed_since_checkpoint >= checkpoint_every:
                    _write_jsonl_atomic(path, records)
                    changed_since_checkpoint = 0
                    _progress(f"{path.name}: checkpoint enriched={summary.records_enriched}")
                time.sleep(sleep_seconds)
            else:
                records[index] = _mark_fulltext_attempt(record, source=source, status="no_fulltext", reason="no_extractable_text")
                changed = True
                changed_since_checkpoint += 1
                if source != "arxiv":
                    summary.errors += 1
                if checkpoint_every > 0 and changed_since_checkpoint >= checkpoint_every:
                    _write_jsonl_atomic(path, records)
                    changed_since_checkpoint = 0
                    _progress(f"{path.name}: checkpoint enriched={summary.records_enriched}")
        if changed:
            _write_jsonl_atomic(path, records)
        if remaining is not None and remaining <= 0:
            break
        if remaining_attempts is not None and remaining_attempts <= 0:
            break

    return summary.__dict__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sciscope-fulltext-enrichment")
    parser.add_argument("--canonical-dir", type=Path, default=Path("data/raw_canonical"))
    parser.add_argument("--source", default="arxiv", choices=SUPPORTED_SOURCES)
    parser.add_argument("--years", default="2022,2023,2024,2025,2026")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sleep-seconds", type=float, default=3.0)
    parser.add_argument("--text-limit", type=int, default=DEFAULT_TEXT_LIMIT)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-download-bytes", type=int, default=DEFAULT_MAX_DOWNLOAD_BYTES)
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--field-filter")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--no-browser-fallback", action="store_true")
    parser.add_argument("--stable-only", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    years = [year.strip() for year in args.years.split(",") if year.strip()]
    summary = enrich_fulltext_in_place(
        canonical_dir=args.canonical_dir,
        source=args.source,
        years=years,
        limit=args.limit,
        sleep_seconds=args.sleep_seconds,
        text_limit=args.text_limit,
        timeout_seconds=args.timeout_seconds,
        max_download_bytes=args.max_download_bytes,
        max_attempts=args.max_attempts,
        checkpoint_every=args.checkpoint_every,
        browser_fallback=not args.no_browser_fallback,
        stable_only=args.stable_only,
        field_filter=args.field_filter,
        retry_failed=args.retry_failed,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
