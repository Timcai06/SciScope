from fastapi import APIRouter, Response

from backend.app.core.config import get_settings
from backend.app.services.readiness_service import readiness_report

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name}


@router.get("/readyz")
def readyz(response: Response) -> dict[str, object]:
    status_code, body = readiness_report(get_settings())
    response.status_code = status_code
    return body
