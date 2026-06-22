"""Trend / forecasting model for SciScope.

Consumes the descriptive analysis assets (``keyword_trends.csv``,
``keyword_lifecycle.csv``, ``topic_year_share.csv``, ``topic_keywords.csv``) and
turns them into a forecast model: per-keyword growth, acceleration, burst,
a linear next-year projection with a rough uncertainty band, and a composite
hotness score. Topic trends are projected the same way.

Outputs (the deliverable "trend model files"):
    models/trends/hot_keywords.csv
    models/trends/topic_trends.csv
    models/trends/trend_scores.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.models.keyword_filter import is_noise_keyword

ANALYSIS_DIR = Path("data/analysis")
OUTPUT_DIR = Path("models/trends")
MIN_DOC_COUNT = 30
TOP_N = 500
_YEAR_COL_RE = re.compile(r"normalized_df_(\d{4})$")


def _year_columns(df: pd.DataFrame) -> list[tuple[int, str]]:
    pairs = []
    for col in df.columns:
        m = _YEAR_COL_RE.match(col)
        if m:
            pairs.append((int(m.group(1)), col))
    return sorted(pairs)


def _fit_forecast(years: np.ndarray, values: np.ndarray) -> dict[str, float]:
    """Linear least-squares forecast of the next year with a rough 95% band."""
    n = len(years)
    if n < 2 or np.allclose(values, values[0]):
        flat = float(values[-1]) if n else 0.0
        return {"slope": 0.0, "r2": 0.0, "forecast": flat, "low": flat, "high": flat}

    slope, intercept = np.polyfit(years, values, 1)
    pred = slope * years + intercept
    residuals = values - pred
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((values - values.mean()) ** 2)) or 1e-12
    r2 = max(0.0, 1.0 - ss_res / ss_tot)

    next_year = int(years.max()) + 1
    # Damped trend: anchor on the actual last value and add a damped slope.
    # A 3-point OLS slope extrapolated raw overshoots (worse than persistence);
    # damping (phi<1) keeps the forecast between persistence and full linear.
    phi = 0.5
    forecast = float(values[-1] + phi * slope * (next_year - years[-1]))
    # Rough prediction std from residuals (small-sample, advisory only).
    dof = max(1, n - 2)
    se = float(np.sqrt(ss_res / dof))
    margin = 1.96 * se
    return {
        "slope": float(slope),
        "r2": round(r2, 4),
        "forecast": max(0.0, round(forecast, 8)),
        "low": max(0.0, round(forecast - margin, 8)),
        "high": round(forecast + margin, 8),
        "next_year": next_year,
    }


def _minmax(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-12:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo)


def build_keyword_trends(analysis_dir: Path) -> pd.DataFrame:
    trends = pd.read_csv(analysis_dir / "keyword_trends.csv")
    trends = trends[trends["doc_count"] >= MIN_DOC_COUNT].copy()
    # Drop category codes (cs.lg ...) and over-generic labels (computer science ...).
    trends = trends[~trends["keyword"].astype(str).map(is_noise_keyword)].copy()
    year_cols = _year_columns(trends)
    if not year_cols:
        raise ValueError("keyword_trends.csv has no normalized_df_<year> columns")
    # The latest year is partial (year-to-date); fit on complete years only.
    full_years = [(y, c) for y, c in year_cols][:-1] or year_cols
    years = np.array([y for y, _ in full_years], dtype=float)

    forecasts = []
    for _, row in trends.iterrows():
        values = np.array([float(row.get(c, 0.0) or 0.0) for _, c in full_years])
        forecasts.append(_fit_forecast(years, values))
    fc = pd.DataFrame(forecasts, index=trends.index)
    trends["forecast_next_year"] = fc["next_year"] if "next_year" in fc else int(years.max()) + 1
    trends["forecast_normalized_df"] = fc["forecast"]
    trends["forecast_low"] = fc["low"]
    trends["forecast_high"] = fc["high"]
    trends["trend_slope"] = fc["slope"]
    trends["trend_r2"] = fc["r2"]

    # Optional lifecycle context.
    lifecycle_path = analysis_dir / "keyword_lifecycle.csv"
    if lifecycle_path.exists():
        lifecycle = pd.read_csv(lifecycle_path)[["keyword", "lifecycle_stage", "peak_year"]]
        trends = trends.merge(lifecycle, on="keyword", how="left")

    # Composite hotness: blend momentum, burst, and forecast slope.
    trends["trend_score"] = (
        0.5 * _minmax(trends["momentum_score"].fillna(0))
        + 0.3 * _minmax(trends["burst_score"].fillna(0))
        + 0.2 * _minmax(trends["trend_slope"].fillna(0))
    ).round(6)
    return trends.sort_values("trend_score", ascending=False)


def build_topic_trends(analysis_dir: Path) -> pd.DataFrame:
    share = pd.read_csv(analysis_dir / "topic_year_share.csv")
    keywords = pd.read_csv(analysis_dir / "topic_keywords.csv")
    pivot = (
        share.pivot_table(index=["model", "topic_id"], columns="year", values="paper_count", fill_value=0)
        .reset_index()
    )
    year_cols = sorted(c for c in pivot.columns if isinstance(c, (int, np.integer)))
    fit_years = year_cols[:-1] or year_cols
    years = np.array([float(y) for y in fit_years])

    rows = []
    for _, row in pivot.iterrows():
        values = np.array([float(row[y]) for y in fit_years])
        fc = _fit_forecast(years, values)
        rows.append({"forecast_next_year": fc.get("next_year"), "forecast_paper_count": fc["forecast"], "trend_slope": fc["slope"]})
    fc_df = pd.DataFrame(rows, index=pivot.index)
    out = pd.concat([pivot, fc_df], axis=1)
    out = out.merge(keywords, on=["model", "topic_id"], how="left")
    return out


def _scores_summary(keywords: pd.DataFrame, years: list[int]) -> dict:
    def top(df: pd.DataFrame, n=20) -> list[dict]:
        cols = [
            "keyword", "doc_count", "normalized_df", "momentum_score", "burst_score",
            "trend_slope", "forecast_normalized_df", "forecast_low", "forecast_high",
            "trend_r2", "trend_score", "lifecycle_stage", "representative_title", "representative_year",
        ]
        cols = [c for c in cols if c in df.columns]
        return df[cols].head(n).to_dict(orient="records")

    emerging = keywords[keywords["trend_slope"] > 0].sort_values("trend_score", ascending=False)
    declining = keywords.sort_values("trend_slope").head(20)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fit_years": years,
        "min_doc_count": MIN_DOC_COUNT,
        "keywords_modeled": int(len(keywords)),
        "method": "linear least-squares on full-year normalized document frequency; "
        "latest (partial) year excluded from fit; 95% band from residual std (small-sample, advisory).",
        "uncertainty_note": "Forecasts use 4-5 yearly points; treat bands as indicative, not statistical guarantees.",
        "top_hot": top(keywords, 30),
        "top_emerging": top(emerging, 20),
        "top_declining": declining[["keyword", "trend_slope", "lifecycle_stage"]].to_dict(orient="records")
        if "lifecycle_stage" in declining else declining[["keyword", "trend_slope"]].to_dict(orient="records"),
    }


def run(analysis_dir: Path = ANALYSIS_DIR, output_dir: Path = OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    keywords = build_keyword_trends(analysis_dir)
    topics = build_topic_trends(analysis_dir)

    hot_cols = [
        "keyword", "doc_count", "normalized_df", "growth_rate", "momentum_score", "burst_score",
        "trend_slope", "trend_r2", "forecast_next_year", "forecast_normalized_df",
        "forecast_low", "forecast_high", "trend_score", "lifecycle_stage", "peak_year",
        "representative_paper_id", "representative_title", "representative_year",
    ]
    hot_cols = [c for c in hot_cols if c in keywords.columns]
    keywords.head(TOP_N)[hot_cols].to_csv(output_dir / "hot_keywords.csv", index=False)
    topics.to_csv(output_dir / "topic_trends.csv", index=False)

    fit_years = [int(y) for y, _ in _year_columns(pd.read_csv(analysis_dir / "keyword_trends.csv"))][:-1]
    summary = _scores_summary(keywords, fit_years)
    (output_dir / "trend_scores.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"hot_keywords": min(TOP_N, len(keywords)), "topics": int(len(topics)), "fit_years": fit_years}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SciScope trend/forecast model")
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.analysis_dir, args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
