"""LangChain chat model factory. Provider and keys come from settings."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger, log_event

logger = get_logger(__name__)

NVIDIA_CHAT_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


class LLMConfigError(RuntimeError):
    """Raised when the LLM provider cannot be constructed."""


def resolve_llm_api_key(settings: Settings | None = None) -> str | None:
    """Return the chat-model key. NVIDIA_API_KEY is accepted as a fallback."""

    settings = settings or get_settings()
    for secret in (settings.llm_api_key, settings.nvidia_api_key):
        if secret is None:
            continue
        value = secret.get_secret_value().strip()
        if value:
            return value
    return None


def llm_is_configured(settings: Settings | None = None) -> bool:
    return resolve_llm_api_key(settings) is not None


def build_chat_model(settings: Settings | None = None) -> Any:
    """Return a LangChain chat model. API keys are never logged."""

    settings = settings or get_settings()
    api_key = resolve_llm_api_key(settings)
    if not api_key:
        raise LLMConfigError("LLM_API_KEY is not configured")

    provider = settings.llm_provider.strip().lower()
    timeout = float(settings.llm_timeout_seconds)
    log_event(logger, "llm_client_configured", provider=provider, model=settings.llm_model)

    if provider in {"openai", "openai_compatible", "nvidia"}:
        from langchain_openai import ChatOpenAI

        model_name = settings.llm_model
        base_url = settings.llm_base_url
        if provider == "nvidia":
            base_url = base_url or NVIDIA_CHAT_URL
            if model_name.startswith("gpt-"):
                model_name = NVIDIA_DEFAULT_MODEL
        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "temperature": settings.llm_temperature,
            "timeout": timeout,
        }
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.llm_model,
            api_key=api_key,
            temperature=settings.llm_temperature,
            timeout=timeout,
        )

    raise LLMConfigError(f"unsupported LLM provider: {provider}")
