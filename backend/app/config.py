"""Central settings, loaded from .env. No secret is ever hardcoded here."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings read from environment / .env file."""

    database_url: str
    database_url_readonly: str = ""
    llm_provider: str = "anthropic"
    llm_model: str = ""
    llm_api_key: str = ""
    sql_statement_timeout_ms: int = 5000
    sql_max_limit: int = 200

    model_config = SettingsConfigDict(
        # .env lives at the repo root, one level above backend/
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
