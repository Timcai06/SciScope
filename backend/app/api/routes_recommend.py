"""Recommendation endpoint for content-similarity suggestions."""

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.schemas import Recommendation, RecommendResponse
from backend.app.services import recommend_service

router = APIRouter(prefix="/api/recommend", tags=["recommend"])


@router.get("", response_model=RecommendResponse)
def recommend(
    paper_id: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
) -> RecommendResponse:
    """Return top similar papers for a given source paper.

    Request/response contract:
    - ``paper_id`` must be a non-empty identifier.
    - ``limit`` controls how many recommendations are included, bounded to [1, 50].
    - Returns ``RecommendResponse`` where each row is a recommendation with scoring
      and traceable rationale factors.

    Error contract:
    - ``503`` when embeddings/recommendation artifacts are missing.
    - ``404`` when no recommendations can be resolved for the target id.
    """
    if not recommend_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Recommendation model not built. Run `make recommend-model` after embeddings.",
        )
    recs = recommend_service.recommend(paper_id, limit=limit)
    if not recs:
        raise HTTPException(status_code=404, detail=f"No recommendations for paper_id={paper_id}")
    return RecommendResponse(
        paper_id=paper_id,
        count=len(recs),
        recommendations=[
            Recommendation(
                paper_id=r.paper_id,
                title=r.title,
                year=r.year,
                field=r.field,
                score=r.score,
                semantic_similarity=r.semantic_similarity,
                shared_keywords=r.shared_keywords,
                shared_authors=r.shared_authors,
                factors=r.factors,
            )
            for r in recs
        ],
    )
