from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv('APP_NAME', 'agentic-code-reviewer')
    environment: str = os.getenv('ENVIRONMENT', 'development')
    github_app_id: str | None = os.getenv('GITHUB_APP_ID')
    github_webhook_secret: str | None = os.getenv('GITHUB_WEBHOOK_SECRET')
    github_private_key: str | None = os.getenv('GITHUB_PRIVATE_KEY')
    github_token: str | None = os.getenv('GITHUB_TOKEN')
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')


settings = Settings()
