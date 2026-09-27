"""Embedding models. Production uses a configurable provider; tests use hashing."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.logging import get_logger, log_event

logger = get_logger(__name__)

HASH_DIMENSIONS = 32


class Embedder(Protocol):
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Deterministic, dependency-free embeddings for tests and offline runs."""

    def __init__(self, dimensions: int = HASH_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text.lower()) or ["_empty"]
        acc = [0.0] * self.dimensions
        for token in tokens[:80]:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            raw = (digest * ((self.dimensions // len(digest)) + 1))[: self.dimensions]
            for index, byte in enumerate(raw):
                acc[index] += (byte / 127.5) - 1.0
        norm = sum(value * value for value in acc) ** 0.5 or 1.0
        return [value / norm for value in acc]


class OpenAIEmbedder:
    def __init__(self, model: str, api_key: str, *, dimensions: int = 1536) -> None:
        from langchain_openai import OpenAIEmbeddings

        self.dimensions = dimensions
        self._model = OpenAIEmbeddings(model=model, api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._model.embed_query(text)


class EmbeddingConfigError(RuntimeError):
    pass


def build_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or get_settings()
    provider = settings.embedding_provider.strip().lower()
    if provider in {"hash", "local", "test"}:
        log_event(logger, "embedder_configured", provider="hash")
        return HashEmbedder()
    api_key = None
    if settings.embedding_api_key is not None:
        api_key = settings.embedding_api_key.get_secret_value()
    elif settings.llm_api_key is not None:
        api_key = settings.llm_api_key.get_secret_value()
    if provider in {"openai", "openai_compatible"} and api_key:
        log_event(logger, "embedder_configured", provider="openai", model=settings.embedding_model)
        return OpenAIEmbedder(settings.embedding_model, api_key)
    if settings.environment == "test":
        return HashEmbedder()
    raise EmbeddingConfigError(f"embedding provider '{provider}' is not configured")
