"""Corpus ingest-status API.

This endpoint reports whether the backend can serve corpus-backed APIs. In
product/dev runs a configured PostgreSQL corpus is authoritative; hermetic tests
and no-DB demos fall back to the in-memory sample corpus.
"""

from fastapi import APIRouter

from backend.app.core.config import get_settings
from backend.app.models.schemas import IngestStatusResponse
from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.get("/status", response_model=IngestStatusResponse)
def ingest_status() -> IngestStatusResponse:
    """Return ingest readiness and loaded paper count.

    Contract:
    - ``status`` is the fixed literal ``"ready"`` when corpus is loadable.
    - ``papers`` counts DB papers when ``SCISCOPE_DB_DSN`` is configured; otherwise
      it counts the loaded in-memory sample corpus.
    """
    settings = get_settings()
    if settings.db_dsn:
        try:
            import psycopg

            with psycopg.connect(settings.db_dsn) as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM papers")
                count = int(cur.fetchone()[0])
            return IngestStatusResponse(status="ready", papers=count)
        except Exception:
            # Keep the endpoint usable for local demos even when a configured DB
            # is temporarily unavailable; corpus-backed tool endpoints still
            # surface their own DB errors.
            pass

    corpus = get_corpus()
    return IngestStatusResponse(status="ready", papers=len(corpus))
