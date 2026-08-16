"""Dependency wiring. The one place a concrete store is chosen."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings
from app.core.ratelimit import SlidingWindowLimiter, client_ip
from app.domain.models import PricingCatalogue
from app.domain.pricing_data import build_catalogue
from app.repositories.base import LeadRepository
from app.repositories.memory import MemoryLeadRepository
from app.services.ref_service import FileSequenceStore, QuoteRefAllocator

SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache
def _repository(lead_store: str, sheet_id: str, credentials: str) -> LeadRepository:
    if lead_store == "sheets":
        # Imported lazily so M0/M1 need no Google dependency installed at all.
        from app.repositories.sheets import SheetsLeadRepository

        return SheetsLeadRepository(sheet_id=sheet_id, credentials_path=credentials)
    return MemoryLeadRepository()


def get_repository(settings: SettingsDep) -> LeadRepository:
    # Chosen by the explicit LEAD_STORE setting, never inferred from whether
    # SHEET_ID happens to be filled in — a half-configured .env must fail loudly
    # rather than silently dropping every lead on the floor.
    return _repository(settings.lead_store, settings.sheet_id, settings.google_service_account_json)


@lru_cache
def _allocator(path: str) -> QuoteRefAllocator:
    return QuoteRefAllocator(FileSequenceStore(path))


def get_ref_allocator(settings: SettingsDep) -> QuoteRefAllocator:
    return _allocator(settings.quote_seq_path)


@lru_cache
def _catalogue(
    minimum_callout: int, pct: int, requires_visit: bool, from_job: int
) -> PricingCatalogue:
    return build_catalogue(
        minimum_callout=minimum_callout,
        recurring_discount_pct=pct,
        recurring_requires_visit=requires_visit,
        recurring_discount_from_job=from_job,
    )


def get_catalogue(settings: SettingsDep) -> PricingCatalogue:
    return _catalogue(
        settings.minimum_callout,
        settings.recurring_discount_pct,
        settings.recurring_requires_visit,
        settings.recurring_discount_from_job,
    )


@lru_cache
def _limiter(per_min: int, per_hour: int) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(per_min, per_hour)


def get_quote_limiter(settings: SettingsDep) -> SlidingWindowLimiter:
    return _limiter(settings.rate_limit_quote_per_min, settings.rate_limit_quote_per_hour)


def rate_limit_quote(
    request: Request,
    limiter: Annotated[SlidingWindowLimiter, Depends(get_quote_limiter)],
) -> None:
    allowed, retry_after = limiter.check(client_ip(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many quotes from this device. Please try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


RepositoryDep = Annotated[LeadRepository, Depends(get_repository)]
CatalogueDep = Annotated[PricingCatalogue, Depends(get_catalogue)]
AllocatorDep = Annotated[QuoteRefAllocator, Depends(get_ref_allocator)]
