"""Configuration loading tests."""

import os
from unittest.mock import patch

from app.core.config import Settings, clear_settings_cache, get_settings


def test_settings_use_environment_variables() -> None:
    env = {
        "APP_NAME": "custom-reviewer",
        "ENVIRONMENT": "development",
        "DATABASE_URL": "postgresql+psycopg://user:pass@db:5432/app",
        "LLM_PROVIDER": "anthropic",
        "LLM_API_KEY": "sk-test-not-real",
    }
    with patch.dict(os.environ, env, clear=False):
        settings = Settings()

    assert settings.app_name == "custom-reviewer"
    assert str(settings.database_url).startswith("postgresql+psycopg://")
    assert settings.llm_provider == "anthropic"
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test-not-real"
    assert "sk-test" not in repr(settings.llm_api_key)
    assert settings.github_post_reviews is True
    assert "localhost:5173" in settings.cors_origins


def test_get_settings_is_cached() -> None:
    clear_settings_cache()
    first = get_settings()
    second = get_settings()
    assert first is second
    clear_settings_cache()
