"""GET /api/pricing — the whole catalogue (ARCHITECTURE.md §5).

The frontend renders its options from this and computes a live client-side
estimate off it, so no price is ever hardcoded in TypeScript. The server total
remains the quote of record.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import CatalogueDep
from app.domain.models import PricingCatalogue

router = APIRouter(tags=["pricing"])


@router.get("/pricing", response_model=PricingCatalogue, summary="Price catalogue")
def pricing(catalogue: CatalogueDep, response: Response) -> PricingCatalogue:
    # Prices change rarely and the app targets slow mobile data; a short public
    # cache lets Cloudflare's Nairobi edge serve most of these.
    response.headers["Cache-Control"] = "public, max-age=300"
    return catalogue
