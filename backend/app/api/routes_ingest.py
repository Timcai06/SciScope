"""Corpus ingest-status API.

This endpoint reports whether the backend can serve corpus-backed APIs by surfacing
the current sample data load size.
"""

from fastapi import APIRouter

from backend.app.models.schemas import IngestStatusResponse
from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.get("/status", response_model=IngestStatusResponse)
def ingest_status() -> IngestStatusResponse:
    """Return ingest readiness and loaded paper count.

    Contract:
    - ``status`` is the fixed literal ``"ready"`` when corpus is loadable.
    - ``papers`` counts how many records are currently in memory.
    """
    corpus = get_corpus()
    return IngestStatusResponse(status="ready", papers=len(corpus))
