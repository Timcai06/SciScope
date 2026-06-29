from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.config import Settings


@dataclass(frozen=True)
class ReadinessCheck:
    status: str
    message: str


def check_database_config(settings: Settings) -> ReadinessCheck:
    if not settings.db_dsn.strip():
        return ReadinessCheck("missing", "SCISCOPE_DB_DSN is required for hosted readiness")
    return ReadinessCheck("configured", "database DSN configured")


def check_model_config(settings: Settings) -> ReadinessCheck:
    if settings.use_mock_llm:
        return ReadinessCheck("mock", "mock LLM is enabled")
    if settings.llm_provider == "deepseek" and not settings.deepseek_api_key.strip():
        return ReadinessCheck("missing", "DEEPSEEK_API_KEY is required when DeepSeek is active")
    return ReadinessCheck("configured", f"{settings.llm_provider} provider configured")


def readiness_report(settings: Settings) -> tuple[int, dict[str, Any]]:
    checks = {
        "db": check_database_config(settings),
        "model": check_model_config(settings),
    }
    ready = all(check.status in {"configured"} for check in checks.values())
    body = {
        "status": "ready" if ready else "not_ready",
        "checks": {
            name: {"status": check.status, "message": check.message}
            for name, check in checks.items()
        },
    }
    return (200 if ready else 503), body
