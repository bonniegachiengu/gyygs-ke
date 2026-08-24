"""Route registry. Every router mounts under `/api`."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, health, pricing, quote

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(pricing.router)
api_router.include_router(quote.router)

# admin carries its own full "/api/admin" prefix and is mounted on the app
# directly in main.py -- including it here would double the /api segment.
admin_router = admin.router

__all__ = ["api_router", "admin_router"]
