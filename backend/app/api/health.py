"""Liveness and readiness endpoint."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.database.session import check_database_connection
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse},
    },
)
def health_check() -> HealthResponse | JSONResponse:
    """Report process liveness and PostgreSQL connectivity."""

    settings = get_settings()
    payload = {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "database": "connected",
        "detail": None,
    }

    try:
        check_database_connection()
    except Exception as exc:
        log_event(logger, "health_check_database_unavailable", error_type=type(exc).__name__)
        payload["status"] = "degraded"
        payload["database"] = "unavailable"
        payload["detail"] = "database connection failed"
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)

    return HealthResponse.model_validate(payload)
