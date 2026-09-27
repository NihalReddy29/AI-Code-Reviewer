"""API schemas for health checks."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    environment: str
    database: Literal["connected", "unavailable"]
    detail: str | None = Field(default=None)
