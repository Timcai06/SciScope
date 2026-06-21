from fastapi import APIRouter, HTTPException, Query

from backend.app.models.schemas import GraphResponse
from backend.app.services import graph_service

router = APIRouter(prefix="/api/graph", tags=["graph"])

_TYPES = {"author", "keyword", "topic"}


@router.get("", response_model=GraphResponse)
def graph(
    type: str = Query(default="keyword"),
    center: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> GraphResponse:
    if type not in _TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(_TYPES)}")
    if not graph_service.is_available():
        raise HTTPException(status_code=503, detail="Graphs not built. Run `make graph-export`.")
    data = graph_service.graph(type, center=center, limit=limit)
    return GraphResponse(**data)
