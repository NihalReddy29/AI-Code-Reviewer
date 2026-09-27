"""LLM factory tests. Does not call a real provider."""

import pytest

from app.core.config import Settings
from app.core.llm import LLMConfigError, build_chat_model, llm_is_configured


def test_llm_is_configured_requires_key() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        llm_api_key=None,
        nvidia_api_key=None,
        github_token=None,
    )
    assert llm_is_configured(settings) is False


def test_unsupported_provider_raises() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        llm_provider="unknown-vendor",
        llm_api_key="sk-test",
        github_token=None,
    )
    with pytest.raises(LLMConfigError, match="unsupported"):
        build_chat_model(settings)


def test_nvidia_key_counts_as_configured() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        llm_api_key=None,
        nvidia_api_key="nvapi-test-not-real",
        github_token=None,
    )
    assert llm_is_configured(settings) is True


def test_nvidia_provider_uses_catalog_base_url() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        llm_provider="nvidia",
        llm_model="gpt-4o-mini",
        nvidia_api_key="nvapi-test-not-real",
        github_token=None,
    )
    model = build_chat_model(settings)
    base = getattr(model, "openai_api_base", None) or str(getattr(model, "base_url", ""))
    assert "integrate.api.nvidia.com" in str(base)
    model_name = getattr(model, "model_name", None) or getattr(model, "model", "")
    assert "nemotron" in str(model_name)
