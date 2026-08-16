"""Route registry. Every router mounts under `/api`."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)

__all__ = ["api_router"]
