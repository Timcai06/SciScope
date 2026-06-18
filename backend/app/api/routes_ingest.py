from fastapi import APIRouter

from backend.app.models.schemas import IngestStatusResponse
from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.get("/status", response_model=IngestStatusResponse)
def ingest_status() -> IngestStatusResponse:
    corpus = get_corpus()
    return IngestStatusResponse(status="ready", papers=len(corpus))
