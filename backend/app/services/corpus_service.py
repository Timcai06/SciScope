"""Corpus loading boundary for in-memory workflows."""

from functools import lru_cache
from typing import Any

from backend.app.core.config import get_settings
from data_pipeline.loaders import load_papers


@lru_cache(maxsize=1)
def get_corpus() -> list[dict[str, Any]]:
    """Load configured corpus once per process and cache for service callers."""
    settings = get_settings()
    return load_papers(settings.data_path)
