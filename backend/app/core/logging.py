"""Structured JSON logging with secret redaction and review-run context."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings

review_run_id_var: ContextVar[str | None] = ContextVar("review_run_id", default=None)

_SECRET_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "github_token",
    "github_private_key",
    "github_webhook_secret",
    "llm_api_key",
    "nvidia_api_key",
    "embedding_api_key",
    "qdrant_api_key",
    "password",
    "secret",
    "private_key",
}

_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization|bearer|private[_-]?key)\s*[:=]\s*.+"
)


def set_review_run_id(review_run_id: str | None) -> None:
    """Bind the current review run to subsequent log records."""

    review_run_id_var.set(review_run_id)


def get_review_run_id() -> str | None:
    return review_run_id_var.get()


def redact(value: Any) -> Any:
    """Recursively redact secret-looking keys and inline credential patterns."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in _SECRET_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_PATTERN.sub(r"\1=[REDACTED]", value)
    return value


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for machine-readable traces."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        review_run_id = getattr(record, "review_run_id", None) or get_review_run_id()
        if review_run_id:
            payload["review_run_id"] = review_run_id

        extra = getattr(record, "extra_data", None)
        if isinstance(extra, dict):
            payload.update(redact(extra))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class ReviewRunFilter(logging.Filter):
    """Copy the context-local review_run_id onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "review_run_id", None):
            record.review_run_id = get_review_run_id()
        return True


def configure_logging(settings: Settings | None = None) -> None:
    """Configure root logging once. Safe to call from tests and app startup."""

    settings = settings or get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ReviewRunFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    """Log a structured event. Extra fields are JSON-encoded and redacted."""

    logger.info(message, extra={"extra_data": fields})
