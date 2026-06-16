import re
from typing import Any


def normalize_keyword(value: str) -> str:
    cleaned = value.strip().lower().replace("-", " ")
    return re.sub(r"\s+", " ", cleaned)


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace(",", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def normalize_paper(raw: dict[str, Any]) -> dict[str, Any]:
    keywords = [normalize_keyword(item) for item in _split_list(raw.get("keywords"))]
    authors = _split_list(raw.get("authors"))
    year_value = raw.get("year")
    year = int(year_value) if str(year_value).strip().isdigit() else None
    field = str(raw.get("field") or "unknown").strip().lower() or "unknown"
    return {
        "paper_id": str(raw.get("paper_id", "")).strip(),
        "title": str(raw.get("title", "")).strip(),
        "abstract": str(raw.get("abstract") or "").strip(),
        "authors": authors,
        "year": year,
        "keywords": keywords,
        "field": field,
        "full_text": str(raw.get("full_text") or "").strip(),
    }
