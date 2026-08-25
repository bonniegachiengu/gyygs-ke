"""POST /api/quote — the authoritative quote (ARCHITECTURE.md §5).

The client may show a live estimate, but this is the quote of record: the server
recomputes from the selections, mints the reference, builds the wa.me URL and
logs the lead.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (AllocatorDep, CatalogueDep, RepositoryDep, SettingsDep,
                          TransportDep, rate_limit_quote)
from app.domain.models import QuoteRequest, QuoteResponse
from app.services.quote_service import create_quote

router = APIRouter(tags=["quote"])


@router.post(
    "/quote",
    response_model=QuoteResponse,
    dependencies=[Depends(rate_limit_quote)],
    summary="Price a basket and build the WhatsApp handoff",
)
def post_quote(
    req: QuoteRequest,
    catalogue: CatalogueDep,
    repo: RepositoryDep,
    refs: AllocatorDep,
    settings: SettingsDep,
    transport: TransportDep,
) -> QuoteResponse:
    return create_quote(
        req,
        cat=catalogue,
        repo=repo,
        refs=refs,
        whatsapp_number=settings.whatsapp_number,
        site_host=settings.public_site_host,
        vat_registered=settings.vat_registered,
        vat_rate=settings.vat_rate,
        transport=transport.fee_for(req.area),
    )


@router.post(
    "/quote/{quote_ref}/sent",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a quote as handed off to WhatsApp",
)
def mark_sent(quote_ref: str, repo: RepositoryDep) -> None:
    """Beacon from the Send button.

    Without it every lead would sit at sent_to_wa=false and the drop-off metric
    SPEC §8 asks for would be meaningless. Idempotent — the button is guarded
    against double-taps, but a retried beacon must not be an error.
    """
    if not repo.mark_sent(quote_ref):
        raise HTTPException(status_code=404, detail="unknown quote reference")
