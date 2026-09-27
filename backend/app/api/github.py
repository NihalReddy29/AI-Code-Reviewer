"""GitHub webhook endpoint."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.database.session import get_db
from app.schemas.github import REVIEWABLE_PULL_REQUEST_ACTIONS, GitHubWebhookPayload
from app.schemas.review import ReviewIngestResponse
from app.services.ingestion import ingest_pull_request, to_response
from app.tools.github import GitHubAPIError, GitHubAuthError, build_github_client, github_is_configured
from app.tools.webhook import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    MAX_WEBHOOK_BYTES,
    SIGNATURE_HEADER,
    WebhookVerificationError,
    verify_github_signature,
)

router = APIRouter(tags=["github"])
logger = get_logger(__name__)

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split("/")
    if len(parts) != 2 or not _NAME_RE.match(parts[0]) or not _NAME_RE.match(parts[1]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid repository full_name")
    return parts[0], parts[1]


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    x_github_event: str | None = Header(default=None, alias=EVENT_HEADER),
    x_github_delivery: str | None = Header(default=None, alias=DELIVERY_HEADER),
) -> ReviewIngestResponse | dict:
    settings = get_settings()
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="webhook payload too large")

    secret = settings.github_webhook_secret
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_WEBHOOK_SECRET is not configured",
        )
    try:
        verify_github_signature(
            payload=raw,
            signature_header=x_hub_signature_256,
            secret=secret.get_secret_value(),
        )
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid webhook signature") from exc

    if x_github_event == "ping":
        log_event(logger, "github_webhook_ping", delivery_id=x_github_delivery)
        return {"status": "ok", "event": "ping"}

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event or "unknown"}

    try:
        payload = GitHubWebhookPayload.model_validate(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        log_event(logger, "github_webhook_malformed", error_type=type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="malformed webhook payload") from exc

    if payload.action not in REVIEWABLE_PULL_REQUEST_ACTIONS:
        return {"status": "ignored", "event": "pull_request", "action": payload.action}

    if payload.repository is None or payload.pull_request is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="webhook missing repository or pull_request")

    if not github_is_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub API credentials are not configured",
        )

    owner, repo = _split_full_name(payload.repository.full_name)
    number = payload.pull_request.number
    try:
        with build_github_client(owner, repo, settings=settings) as client:
            result = ingest_pull_request(
                db,
                client,
                owner=owner,
                repo=repo,
                number=number,
                trigger=f"webhook:{payload.action}",
                delivery_id=x_github_delivery,
            )
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GitHub authentication failed") from exc
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="failed to fetch pull request from GitHub",
        ) from exc

    response = to_response(result, trigger=f"webhook:{payload.action}")
    return response
