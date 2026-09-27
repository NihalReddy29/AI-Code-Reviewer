"""Shared pytest fixtures. Database URL is set before application imports."""

from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["APP_NAME"] = "ai-code-reviewer-test"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["GITHUB_TOKEN"] = "ghs_test_token_not_real"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["QDRANT_URL"] = ":memory:"
os.environ["NVIDIA_API_KEY"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "openai"

from collections.abc import Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import clear_settings_cache  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

clear_settings_cache()
configure_logging()
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def _reset_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(_reset_database) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(_reset_database) -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
