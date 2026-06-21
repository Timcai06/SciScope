"""Serve the trend/forecast model files to the API.

Reads ``models/trends/trend_scores.json`` (summary + ranked lists) and, for
per-keyword series, the per-year ``normalized_df_<year>`` columns of
``data/analysis/keyword_trends.csv``. Files are loaded lazily and cached.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

TREND_DIR = Path(os.getenv("SCISCOPE_TREND_DIR", "models/trends"))
ANALYSIS_DIR = Path(os.getenv("SCISCOPE_ANALYSIS_DIR", "data/analysis"))
_YEAR_COL_RE = re.compile(r"normalized_df_(\d{4})$")


def is_available() -> bool:
    return (TREND_DIR / "trend_scores.json").exists()


@lru_cache(maxsize=1)
def _scores() -> dict[str, Any]:
    path = TREND_DIR / "trend_scores.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _forecast_year(scores: dict[str, Any]) -> int | None:
    fit_years = scores.get("fit_years") or []
    return (max(fit_years) + 1) if fit_years else None


def _clean(value: Any) -> Any:
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


_INT_FIELDS = {"doc_count", "representative_year", "forecast_year"}
_KEEP_FIELDS = {
    "keyword", "doc_count", "normalized_df", "momentum_score", "burst_score",
    "trend_slope", "trend_r2", "forecast_year", "forecast_normalized_df",
    "forecast_low", "forecast_high", "trend_score", "lifecycle_stage",
    "representative_title", "representative_year",
}


def _normalize_item(raw: dict[str, Any], forecast_year: int | None) -> dict[str, Any]:
    item = {k: _clean(v) for k, v in raw.items() if k in _KEEP_FIELDS}
    item.setdefault("forecast_year", forecast_year)
    for field in _INT_FIELDS:
        if isinstance(item.get(field), float):
            item[field] = int(item[field])
    return item


def overview(hot_limit: int = 30, emerging_limit: int = 20) -> dict[str, Any]:
    scores = _scores()
    fy = _forecast_year(scores)
    return {
        "generated_at": scores.get("generated_at"),
        "fit_years": scores.get("fit_years", []),
        "forecast_year": fy,
        "method": scores.get("method", ""),
        "uncertainty_note": scores.get("uncertainty_note", ""),
        "top_hot": [_normalize_item(i, fy) for i in scores.get("top_hot", [])[:hot_limit]],
        "top_emerging": [_normalize_item(i, fy) for i in scores.get("top_emerging", [])[:emerging_limit]],
    }


@lru_cache(maxsize=1)
def _keyword_year_cols() -> tuple[list[tuple[int, str]], dict[str, dict[str, float]]]:
    """Return (year_columns, {keyword: row}) from keyword_trends.csv."""
    import csv

    path = ANALYSIS_DIR / "keyword_trends.csv"
    rows: dict[str, dict[str, float]] = {}
    year_cols: list[tuple[int, str]] = []
    if not path.exists():
        return year_cols, rows
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for col in reader.fieldnames or []:
            m = _YEAR_COL_RE.match(col)
            if m:
                year_cols.append((int(m.group(1)), col))
        year_cols.sort()
        for row in reader:
            rows[row["keyword"]] = row
    return year_cols, rows


def keyword_series(keyword: str) -> list[dict[str, Any]]:
    year_cols, rows = _keyword_year_cols()
    row = rows.get(keyword)
    if not row:
        return []
    series = []
    for year, col in year_cols:
        try:
            series.append({"year": year, "normalized_df": float(row.get(col) or 0.0)})
        except (TypeError, ValueError):
            continue
    return series
