"""GET /api/pricing — the whole catalogue (ARCHITECTURE.md §5).

The frontend renders its options from this and computes a live client-side
estimate off it, so no price is ever hardcoded in TypeScript. The server total
remains the quote of record.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import CatalogueDep, TransportDep
from app.domain.models import PricingCatalogue

router = APIRouter(tags=["pricing"])


@router.get("/pricing", response_model=PricingCatalogue, summary="Price catalogue")
def pricing(catalogue: CatalogueDep, transport: TransportDep,
            response: Response) -> PricingCatalogue:
    # Prices change rarely and the app targets slow mobile data; a short public
    # cache lets Cloudflare's Nairobi edge serve most of these.
    #
    # Transport fees ride on the areas so the client can show a complete total
    # without a second request. They are read per-request rather than baked into
    # the lru_cached catalogue, because Mercy edits them from the board and a
    # process-lifetime cache would hide her change until a restart. The 5-minute
    # edge cache still applies, but only to the client's PREVIEW: POST /api/quote
    # reads the repository directly, so the authoritative quote always carries
    # the current fee even when a cached catalogue is a few minutes behind.
    response.headers["Cache-Control"] = "public, max-age=300"
    fees = {z["area_key"]: z["fee"] for z in transport.list_zones()}
    return catalogue.model_copy(update={
        "areas": [a.model_copy(update={"transport": fees.get(a.key, 0)})
                  for a in catalogue.areas],
    })
