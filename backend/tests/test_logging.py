"""Structured logging redaction tests."""

import json
import logging
from io import StringIO

from app.core.logging import JsonFormatter, redact, set_review_run_id


def test_redact_secret_keys_and_inline_tokens() -> None:
    payload = {
        "llm_api_key": "sk-secret",
        "nested": {"token": "ghs_abc"},
        "message": "Authorization: Bearer ghs_abc",
    }
    redacted = redact(payload)
    assert redacted["llm_api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert "[REDACTED]" in redacted["message"]
    assert "ghs_abc" not in redacted["message"]


def test_json_formatter_includes_review_run_id() -> None:
    set_review_run_id("run-123")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.logging")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("review_started", extra={"extra_data": {"repository": "acme/api"}})
    record = json.loads(stream.getvalue())
    assert record["message"] == "review_started"
    assert record["review_run_id"] == "run-123"
    assert record["repository"] == "acme/api"
    set_review_run_id(None)
