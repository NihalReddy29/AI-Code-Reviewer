"""GitHub webhook HMAC-SHA256 signature verification."""

from __future__ import annotations

import hashlib
import hmac

from app.core.logging import get_logger

logger = get_logger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"
EVENT_HEADER = "X-GitHub-Event"
DELIVERY_HEADER = "X-GitHub-Delivery"
MAX_WEBHOOK_BYTES = 1_048_576


class WebhookVerificationError(ValueError):
    """Raised when a webhook cannot be authenticated or is too large."""


def verify_github_signature(*, payload: bytes, signature_header: str | None, secret: str) -> None:
    """Validate `X-Hub-Signature-256` using a constant-time compare.

    GitHub signs the raw request body with the webhook secret. Missing or
    malformed signatures are rejected. The secret is never logged.
    """

    if not secret:
        raise WebhookVerificationError("webhook secret is not configured")
    if not payload:
        raise WebhookVerificationError("empty webhook payload")
    if signature_header is None or not signature_header.startswith("sha256="):
        raise WebhookVerificationError("missing or malformed signature header")

    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    expected = f"sha256={digest}"
    if not hmac.compare_digest(expected, signature_header):
        logger.warning("github_webhook_signature_mismatch")
        raise WebhookVerificationError("invalid webhook signature")


def sign_payload(payload: bytes, secret: str) -> str:
    """Create a GitHub-compatible signature. Used by tests."""

    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"
