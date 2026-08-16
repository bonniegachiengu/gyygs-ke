"""Health check — ARCHITECTURE.md §5: `200 -> {"status": "ok", "version": "<semver>"}`."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", version=settings.app_version)
