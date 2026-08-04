"""Read-only API for SciScope's accepted-evidence dispute frontier."""

from fastapi import APIRouter, Query

from backend.app.models.schemas import DisputeItem, DisputesResponse
from backend.app.services.stance.store import disputed_claims

router = APIRouter(prefix="/api/disputes", tags=["evidence"])


@router.get("", response_model=DisputesResponse)
def list_disputes(limit: int = Query(default=20, ge=1, le=100)) -> DisputesResponse:
    """Return claims with both accepted SUPPORT and CONTRADICT evidence.

    An empty list is a truthful initial state: the map only grows after L3
    verification produces evidence meeting its confidence, scope, and sentence
    checks. This endpoint never manufactures a conflict from topical similarity.
    """
    rows = disputed_claims(limit=limit)
    return DisputesResponse(
        count=len(rows),
        disputes=[DisputeItem(**row) for row in rows],
    )
