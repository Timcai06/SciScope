"""Small helpers shared across SciScope tool modules."""

from __future__ import annotations

import json
from typing import Any


def maybe_json(s: str) -> Any:
    """Parse a JSON string back into data, or return it unchanged."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s


def clean_snippet(snippet: str | None, title: str | None, limit: int = 200) -> str:
    """Strip a leading title from a matched chunk so it reads as a pure abstract.

    Retrieval snippets are "title. abstract…"; dropping the title keeps the model
    from confusing it with author names, and truncates to ``limit`` chars.
    """
    snippet = (snippet or "").strip()
    title = (title or "").strip()
    if title and snippet.lower().startswith(title.lower()):
        snippet = snippet[len(title):].lstrip(" .。:：-—")
    return snippet[:limit]


def db_dsn() -> str | None:
    """Resolve the configured Postgres DSN (or None when unavailable)."""
    from backend.app.core.config import get_settings

    return get_settings().db_dsn or None
