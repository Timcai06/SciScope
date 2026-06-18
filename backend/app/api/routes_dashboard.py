from fastapi import APIRouter

from backend.app.models.schemas import DashboardResponse
from backend.app.services.analytics_service import build_dashboard_overview
from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardResponse)
def dashboard_overview() -> DashboardResponse:
    return DashboardResponse(**build_dashboard_overview(get_corpus()))
