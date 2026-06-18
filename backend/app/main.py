from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes_chat import router as chat_router
from backend.app.api.routes_dashboard import router as dashboard_router
from backend.app.api.routes_ingest import router as ingest_router
from backend.app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(dashboard_router)
    app.include_router(chat_router)
    app.include_router(ingest_router)

    return app


app = create_app()
