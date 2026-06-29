"""FastAPI application bootstrap for SciScope backend.

The module wires all API routers into a single app instance and applies shared
runtime configuration (CORS/app metadata) from environment-driven settings.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_agent import router as agent_router
from backend.app.api.routes_chat import router as chat_router
from backend.app.api.routes_dashboard import router as dashboard_router
from backend.app.api.routes_graph import router as graph_router
from backend.app.api.routes_ingest import router as ingest_router
from backend.app.api.routes_recommend import router as recommend_router
from backend.app.api.routes_search import router as search_router
from backend.app.api.routes_trends import router as trends_router
from backend.app.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI app.

    Contract:
    - App title is driven by ``SCISCOPE_APP_NAME``.
    - CORS origins are injected from ``SCISCOPE_CORS_ORIGINS`` (or default local UI origin list).
    - Routes are mounted with their own prefixes from route modules; no route-level
      prefix rewriting is done here.
    """
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    from backend.app.core.request_context import bind_request_context

    @app.middleware("http")
    async def request_context_middleware(request, call_next):
        request_id = bind_request_context(request)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(chat_router)
    app.include_router(ingest_router)
    app.include_router(search_router)
    app.include_router(trends_router)
    app.include_router(recommend_router)
    app.include_router(graph_router)
    app.include_router(agent_router)

    # Opt-in: merge external MCP tools into the agent registry when a config
    # exists (no config = no-op, no external processes). Failures must never
    # block startup.
    from backend.app.agent.mcp_client import CONFIG_PATH, activate_mcp_tools

    if CONFIG_PATH.exists():
        try:
            activate_mcp_tools()
        except Exception:  # noqa: BLE001
            pass

    return app


app = create_app()
