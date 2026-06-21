from fastapi import APIRouter, HTTPException, Query

from backend.app.models.schemas import SearchResponse, SearchResultItem
from backend.app.services import retrieval_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1),
    field: str | None = Query(default=None),
    year: int | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
) -> SearchResponse:
    if not retrieval_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Hybrid retrieval is unavailable. Configure SCISCOPE_DB_DSN and load the corpus.",
        )
    results = retrieval_service.search(q, limit=limit, field=field, year=year)
    return SearchResponse(
        query=q,
        count=len(results),
        results=[
            SearchResultItem(
                paper_id=item.paper_id,
                title=item.title,
                year=item.year,
                field=item.field,
                authors=item.authors,
                snippet=item.snippet,
                score=item.score,
                matched_by=item.matched_by,
            )
            for item in results
        ],
    )
