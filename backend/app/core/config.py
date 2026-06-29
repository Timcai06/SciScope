"""Configuration layer for backend runtime defaults and overrides.

Values come from environment variables and are converted into strongly-typed
settings. Missing values fall back to local-oriented defaults unless explicitly
overridden.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    env: str
    data_path: Path
    cors_origins: list[str]
    llm_provider: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    local_llm_base_url: str
    local_llm_model: str
    local_llm_api_key: str
    use_mock_llm: bool
    db_dsn: str
    embedding_model: str
    anon_requests_per_minute: int
    agent_max_history_turns: int
    agent_max_tool_calls: int
    agent_timeout_seconds: int
    agent_max_question_chars: int
    log_prompts: bool
    trust_proxy_headers: bool


def _parse_bool(value: str | None, default: bool, name: str = "SCISCOPE_USE_MOCK_LLM") -> bool:
    """Parse a boolean env var with permissive truthy/falsy spellings.

    Accepted true values: true/1/yes/y/on
    Accepted false values: false/0/no/n/off
    """
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False

    raise ValueError(f"Invalid {name} value: {value!r}")


def _parse_int(value: str | None, default: int, name: str = "SCISCOPE_INTEGER") -> int:
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(f"Invalid {name} value: {value!r}") from None
    if parsed <= 0:
        raise ValueError(f"Invalid {name} value: {value!r}; expected positive integer")
    return parsed


def _parse_cors_origins(value: str | None) -> list[str]:
    """Parse comma-separated CORS origins with whitespace trimming.

    CORS is opt-in now that the default product path is backend/API + TUI.
    Browser clients can set ``SCISCOPE_CORS_ORIGINS`` explicitly.
    """
    raw_value = value or ""
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Build immutable settings with environment precedence and local-first fallback.

    Resolution rules:
    1) Each field first reads its dedicated environment variable.
    2) If absent, it falls back to a local development default.
    3) DB DSN honors `SCISCOPE_DB_DSN` over legacy `SCISCOPE_DATABASE_URL`.

    This keeps behavior deterministic in tests/dev while still allowing explicit
    deployment override through env vars.
    """
    # Local-first defaults for quick bootstrap:
    # - local app identity/name and default dev sample corpus
    # - localhost CORS + 127.0.0.1 LLM endpoint
    # - mock LLM enabled unless explicitly switched off
    return Settings(
        app_name=os.getenv("SCISCOPE_APP_NAME", "SciScope"),
        env=os.getenv("SCISCOPE_ENV", "local"),
        data_path=Path(os.getenv("SCISCOPE_DATA_PATH", "data/sample/papers.sample.json")),
        cors_origins=_parse_cors_origins(os.getenv("SCISCOPE_CORS_ORIGINS")),
        llm_provider=os.getenv("SCISCOPE_LLM_PROVIDER", "deepseek").strip().lower(),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        local_llm_base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1"),
        local_llm_model=os.getenv("LOCAL_LLM_MODEL", "mlx-community/Qwen2.5-7B-Instruct-4bit"),
        local_llm_api_key=os.getenv("LOCAL_LLM_API_KEY", ""),
        use_mock_llm=_parse_bool(os.getenv("SCISCOPE_USE_MOCK_LLM"), default=True),
        db_dsn=os.getenv("SCISCOPE_DB_DSN", os.getenv("SCISCOPE_DATABASE_URL", "")),
        embedding_model=os.getenv("SCISCOPE_EMBEDDING_MODEL", "intfloat/multilingual-e5-base"),
        anon_requests_per_minute=_parse_int(
            os.getenv("SCISCOPE_ANON_REQUESTS_PER_MINUTE"),
            12,
            name="SCISCOPE_ANON_REQUESTS_PER_MINUTE",
        ),
        agent_max_history_turns=_parse_int(
            os.getenv("SCISCOPE_AGENT_MAX_HISTORY_TURNS"),
            12,
            name="SCISCOPE_AGENT_MAX_HISTORY_TURNS",
        ),
        agent_max_tool_calls=_parse_int(
            os.getenv("SCISCOPE_AGENT_MAX_TOOL_CALLS"),
            8,
            name="SCISCOPE_AGENT_MAX_TOOL_CALLS",
        ),
        agent_timeout_seconds=_parse_int(
            os.getenv("SCISCOPE_AGENT_TIMEOUT_SECONDS"),
            75,
            name="SCISCOPE_AGENT_TIMEOUT_SECONDS",
        ),
        agent_max_question_chars=_parse_int(
            os.getenv("SCISCOPE_AGENT_MAX_QUESTION_CHARS"),
            2000,
            name="SCISCOPE_AGENT_MAX_QUESTION_CHARS",
        ),
        log_prompts=_parse_bool(
            os.getenv("SCISCOPE_LOG_PROMPTS"),
            default=False,
            name="SCISCOPE_LOG_PROMPTS",
        ),
        trust_proxy_headers=_parse_bool(
            os.getenv("SCISCOPE_TRUST_PROXY_HEADERS"),
            default=False,
            name="SCISCOPE_TRUST_PROXY_HEADERS",
        ),
    )
