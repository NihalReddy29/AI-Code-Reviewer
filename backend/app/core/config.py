"""Application settings loaded exclusively from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets stay in env vars, never in source."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "ai-code-reviewer"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    database_url: str = Field(
        default="sqlite+pysqlite:///./local.db",
        description="SQLAlchemy URL. Do not store credentials in the database itself.",
    )

    github_app_id: str | None = None
    github_private_key: SecretStr | None = None
    github_webhook_secret: SecretStr | None = None
    github_token: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    github_post_reviews: bool = True

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: SecretStr | None = None
    nvidia_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_temperature: float = 0.0

    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: SecretStr | None = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "ai_code_reviewer"

    github_timeout_seconds: int = 30
    llm_timeout_seconds: int = 60
    tool_timeout_seconds: int = 120

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached settings instance."""

    return Settings()


def clear_settings_cache() -> None:
    """Reset cached settings. Used by tests when environment variables change."""

    get_settings.cache_clear()
