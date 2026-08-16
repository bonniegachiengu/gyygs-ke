from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_catalogue, get_quote_limiter, get_ref_allocator, get_repository
from app.core.config import Settings, get_settings
from app.core.ratelimit import SlidingWindowLimiter
from app.domain.pricing_data import build_catalogue
from app.main import create_app
from app.repositories.memory import MemoryLeadRepository
from app.services.ref_service import MemorySequenceStore, QuoteRefAllocator

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def settings() -> Settings:
    """Defaults only — never the developer's real .env."""
    return Settings(_env_file=None)


@pytest.fixture
def repo() -> MemoryLeadRepository:
    return MemoryLeadRepository()


@pytest.fixture
def client(settings: Settings, repo: MemoryLeadRepository) -> Iterator[TestClient]:
    app = create_app(settings)

    # Every dependency is overridden so no test touches a real file, a real
    # sheet, or a limiter shared with another test.
    catalogue = build_catalogue(
        minimum_callout=settings.minimum_callout,
        recurring_discount_pct=settings.recurring_discount_pct,
        recurring_requires_visit=settings.recurring_requires_visit,
    )
    allocator = QuoteRefAllocator(MemorySequenceStore())
    limiter = SlidingWindowLimiter(
        settings.rate_limit_quote_per_min, settings.rate_limit_quote_per_hour
    )

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_catalogue] = lambda: catalogue
    app.dependency_overrides[get_ref_allocator] = lambda: allocator
    app.dependency_overrides[get_quote_limiter] = lambda: limiter

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
