from __future__ import annotations

from app.config import settings


def validate_github_token(token: str | None) -> bool:
    if not token:
        return False
    return token.startswith('ghp_') or token.startswith('github_pat_')


def is_github_configured() -> bool:
    return bool(settings.github_token or settings.github_app_id)
