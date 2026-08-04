import re
from typing import Any


def normalize_keyword(value: str) -> str:
    # Canonicalize keywords for stable grouping/search:
    # trim, lowercase and normalize separator/spacing noise.
    cleaned = value.strip().lower().replace("-", " ")
    return re.sub(r"\s+", " ", cleaned)


def _clean_text(value: Any) -> str:
    # Keep missing/empty text as empty string, never as literal "None".
    # This avoids contaminating text fields that expect plain string content.
    if value is None:
        return ""
    return str(value).strip()


def _clean_list_items(value: list[Any]) -> list[str]:
    # Reuse list-item cleaning for authors/keywords while dropping empty tokens.
    return [cleaned for item in value if (cleaned := _clean_text(item))]


def _split_people(value: Any) -> list[str]:
    # Accept both semicolon/pipe-delimited strings and already-list input.
    # Maintain insertion order after trimming and dropping blanks.
    if value is None:
        return []
    if isinstance(value, list):
        return _clean_list_items(value)
    return [part.strip() for part in re.split(r"[;|]", str(value)) if part.strip()]


def _split_keywords(value: Any) -> list[str]:
    # Keep keyword splitting deterministic across common delimiters (comma/semicolon/pipe),
    # while leaving caller-supplied arrays untouched except for cleaning.
    if value is None:
        return []
    if isinstance(value, list):
        return _clean_list_items(value)
    return [part.strip() for part in re.split(r"[;,|]", str(value)) if part.strip()]


def normalize_paper(raw: dict[str, Any]) -> dict[str, Any]:
    # Normalization layer outputs the exact schema expected by later stages:
    # clean scalar text fields, parse year, normalize field, and preserve optional authorship metadata.
    keywords = [normalize_keyword(item) for item in _split_keywords(raw.get("keywords"))]
    authors = _split_people(raw.get("authors"))
    year_value = raw.get("year")
    year = int(year_value) if str(year_value).strip().isdigit() else None
    field = str(raw.get("field") or "unknown").strip().lower() or "unknown"
    paper = {
        "paper_id": _clean_text(raw.get("paper_id")),
        "title": _clean_text(raw.get("title")),
        "abstract": _clean_text(raw.get("abstract")),
        "authors": authors,
        "year": year,
        "keywords": keywords,
        "field": field,
        "full_text": _clean_text(raw.get("full_text")),
    }
    if isinstance(raw.get("authorships"), list):
        paper["authorships"] = raw["authorships"]
    return paper
