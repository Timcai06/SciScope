from fastapi import APIRouter

from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.get("/status")
def ingest_status() -> dict[str, int | str]:
    corpus = get_corpus()
    return {"status": "ready", "papers": len(corpus)}
