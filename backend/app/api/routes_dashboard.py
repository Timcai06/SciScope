"""Dashboard summary API for corpus-wide overview metrics.

The endpoint returns aggregated analytics prepared once per call and derived from the
current corpus loaded by ``get_corpus``.
"""

from fastapi import APIRouter

from backend.app.models.schemas import DashboardResponse
from backend.app.services.analytics_service import build_dashboard_overview
from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardResponse)
def dashboard_overview() -> DashboardResponse:
    """Return global corpus statistics used by the dashboard page."""
    return DashboardResponse(**build_dashboard_overview(get_corpus()))
