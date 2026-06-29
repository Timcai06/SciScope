from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.config import Settings


@dataclass(frozen=True)
class ReadinessCheck:
    status: str
    message: str


def _is_production(settings: Settings) -> bool:
    return settings.env.strip().lower() == "production"


def check_database_config(settings: Settings) -> ReadinessCheck:
    if not settings.db_dsn.strip():
        if _is_production(settings):
            return ReadinessCheck("missing", "SCISCOPE_DB_DSN is required for hosted readiness")
        return ReadinessCheck("sample", "sample corpus mode; SCISCOPE_DB_DSN is not configured")

    try:
        import psycopg

        with psycopg.connect(settings.db_dsn, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM papers LIMIT 1")
                row = cursor.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ReadinessCheck("unavailable", f"database readiness probe failed: {exc}")

    if row is None:
        return ReadinessCheck("unavailable", "database readiness probe returned no paper rows")
    return ReadinessCheck("configured", "database readiness probe succeeded")


def check_model_config(settings: Settings) -> ReadinessCheck:
    if settings.use_mock_llm:
        if _is_production(settings):
            return ReadinessCheck("mock", "mock LLM is not allowed for production readiness")
        return ReadinessCheck("mock", "mock LLM is enabled for local/dev readiness")
    if settings.llm_provider == "deepseek" and not settings.deepseek_api_key.strip():
        return ReadinessCheck("missing", "DEEPSEEK_API_KEY is required when DeepSeek is active")
    return ReadinessCheck("configured", f"{settings.llm_provider} provider configured")


def _status_is_ready(status: str, production: bool) -> bool:
    if production:
        return status == "configured"
    return status in {"configured", "sample", "mock"}


def readiness_report(settings: Settings) -> tuple[int, dict[str, Any]]:
    checks = {
        "db": check_database_config(settings),
        "model": check_model_config(settings),
    }
    production = _is_production(settings)
    ready = all(_status_is_ready(check.status, production) for check in checks.values())
    body = {
        "status": "ready" if ready else "not_ready",
        "checks": {
            name: {"status": check.status, "message": check.message}
            for name, check in checks.items()
        },
    }
    return (200 if ready else 503), body
