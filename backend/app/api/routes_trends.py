"""Trend analysis API for hot topic and emerging keyword outputs."""

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.schemas import TrendsResponse
from backend.app.services import trends_service

router = APIRouter(prefix="/api/trends", tags=["trends"])


@router.get("", response_model=TrendsResponse)
def trends(
    keyword: str | None = Query(default=None),
    hot_limit: int = Query(default=30, ge=1, le=200),
    emerging_limit: int = Query(default=20, ge=1, le=200),
) -> TrendsResponse:
    """Return aggregate trend summaries and optional keyword-specific series.

    - Without ``keyword``: returns global hot/emerging lists.
    - With ``keyword``: injects keyword series from ``trends_service.keyword_series``.
    - Returns bounded list sizes using ``hot_limit`` and ``emerging_limit``.

    Error contract:
    - ``503`` when trend model artifacts are missing (run `make trend-model` first).
    """
    if not trends_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Trend model not built. Run `make trend-model`.",
        )
    data = trends_service.overview(hot_limit=hot_limit, emerging_limit=emerging_limit)
    if keyword:
        data["keyword"] = keyword
        data["series"] = trends_service.keyword_series(keyword)
    return TrendsResponse(**data)
