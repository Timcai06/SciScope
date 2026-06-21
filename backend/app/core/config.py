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


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False

    raise ValueError(f"Invalid SCISCOPE_USE_MOCK_LLM value: {value!r}")


def _parse_cors_origins(value: str | None) -> list[str]:
    raw_value = value if value is not None else "http://localhost:3000"
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def get_settings() -> Settings:
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
    )
