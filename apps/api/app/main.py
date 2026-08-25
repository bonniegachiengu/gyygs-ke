"""FastAPI application factory.

The app is mounted entirely under `/api` (see `app.api.routes.api_router`), which is what
lets the frontend call it same-origin through both the Vite dev proxy and nginx — so there
is no API base URL for the client to get wrong.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (admin_edit_router, admin_quote_router,
                            admin_router, api_router)
from app.core.config import Settings, get_settings
from app.core.errors import DomainError, domain_error_handler


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="Myrah Quote Calculator API",
        version=settings.app_version,
        description=(
            "Server-authoritative pricing for Myrah Cleaning Services. "
            "Prices originate in PRICES.md and are mirrored in app/domain/pricing_data.py."
        ),
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # Locked to the configured web origin. In production the frontend is same-origin
    # behind nginx, so CORS is only actually exercised by local dev on :5173.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # the app has no cookies; every call is stateless
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(api_router)
    app.include_router(admin_router)
    app.include_router(admin_quote_router)
    app.include_router(admin_edit_router)

    return app


app = create_app()
