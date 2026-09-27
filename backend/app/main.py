"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.health import router as health_router
from app.api.github import router as github_router
from app.api.reviews import router as reviews_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger, log_event
from app.database.session import engine, init_database


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger("app.main")
    log_event(logger, "application_starting", environment=settings.environment)
    try:
        init_database()
    except Exception as exc:
        log_event(logger, "database_init_failed", error_type=type(exc).__name__)
    yield
    if settings.environment != "test":
        engine.dispose()
    log_event(logger, "application_stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="AI Code Reviewer",
        version="0.1.0",
        description="Production-oriented GitHub pull request review service.",
        lifespan=lifespan,
    )
    origins = get_settings().cors_origin_list
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        log_event(get_logger("app.main"), "database_request_failed", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "database is unavailable. Start Docker Desktop and run `docker compose up postgres`, or set DATABASE_URL to sqlite.",
            },
        )

    application.include_router(health_router)
    application.include_router(github_router)
    application.include_router(reviews_router)
    return application


app = create_app()
