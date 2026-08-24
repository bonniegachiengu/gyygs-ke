"""Route registry. Every router mounts under `/api`."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, admin_quote, health, pricing, quote

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(pricing.router)
api_router.include_router(quote.router)

# admin carries its own full "/api/admin" prefix and is mounted on the app
# directly in main.py -- including it here would double the /api segment.
admin_router = admin.router
# The operator quote lane. Its own module because it depends on the pricing
# engine, which the rest of the admin surface deliberately does not.
admin_quote_router = admin_quote.router

__all__ = ["api_router", "admin_router", "admin_quote_router"]
