"""The operator lane — Mercy raising a quote from a WhatsApp chat.

`MYRAH_WHATSAPP_AND_CMS.md` §3c: *"the same service chips as the calculator,
powered by the same pricing engine"*, and §3d: *"Reuse the pricing engine for
operator-made quotes -- server-authoritative, one source of truth."*

So this route does NOT price anything itself. It calls `create_quote`, the exact
function `POST /api/quote` calls. There is deliberately no second pricing path:
a second one is how the board and the customer end up seeing different totals
for the same job.

The only difference from the self-serve lane is provenance -- the resulting Job
carries `source=operator` instead of `source=calculator` -- and that Mercy
supplies the customer's details because she has them from the chat.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import AllocatorDep, CatalogueDep, RepositoryDep, SettingsDep, TransportDep
from app.api.routes.admin import JobOut, _repo, _today, require_pin
from app.domain.models import QuoteRequest
from app.domain.operator_extras import OperatorExtras
from app.services.quote_service import create_quote

router = APIRouter(prefix="/api/admin", tags=["admin"])


class OperatorQuoteBody(QuoteRequest):
    """A customer basket plus the operator-only extras.

    Subclassing QuoteRequest keeps the two lanes provably the same shape: the
    operator surface can only ever be the customer's request PLUS something,
    never a different or narrower one.
    """

    operator: OperatorExtras = OperatorExtras()
    #: Raw per-item dicts, carrying note/flags/tags that QuoteItem drops.
    raw_items: list[dict] = []


@router.post("/quotes", dependencies=[Depends(require_pin)])
def operator_quote(
    body: OperatorQuoteBody,
    catalogue: CatalogueDep,
    repo: RepositoryDep,
    refs: AllocatorDep,
    settings: SettingsDep,
    transport: TransportDep,
):
    """Price a basket Mercy has typed from a chat, and land it on the board.

    Returns the quote (so she can send it) AND the board job (so she can act on
    it) from one call -- she is on a phone, mid-conversation, and a second
    round-trip is a second chance to lose the thread.
    """
    req = QuoteRequest.model_validate(body.model_dump(exclude={"operator", "raw_items"}))
    quote = create_quote(
        req,
        cat=catalogue,
        repo=repo,
        refs=refs,
        whatsapp_number=settings.whatsapp_number,
        site_host=settings.public_site_host,
        vat_registered=settings.vat_registered,
        vat_rate=settings.vat_rate,
        transport=transport.fee_for(body.area),
    )

    # create_quote wrote a Lead; re-read it through the job seam and stamp the
    # provenance. Same row, richer reading -- no duplicate record is created.
    jobs = _repo(settings)
    job = jobs.get(quote.quote_ref)
    if job is None:                                  # pragma: no cover
        raise HTTPException(500, "quote was priced but did not land on the board")

    from app.domain.jobs import JobSource
    job = job.model_copy(update={"source": JobSource.OPERATOR})
    jobs.save(job)

    # Operator extras (a custom line, an override) and per-item notes/flags run
    # through the SAME reprice path an edit uses, rather than a second
    # implementation here -- so a deviation is recorded in the change log from
    # the job's first moment, exactly as a later one would be.
    if not body.operator.empty or body.raw_items:
        from app.api.routes.admin_edit import RepriceBody, reprice
        reprice(
            quote.quote_ref,
            RepriceBody(
                items=body.raw_items or [i.model_dump() for i in body.items],
                addons=[a.model_dump() for a in body.addons],
                reason="raised with operator detail",
                operator=body.operator,
            ),
            catalogue,
            settings,
        )
        job = jobs.get(quote.quote_ref)

    return {
        "ok": True,
        "quote_ref": quote.quote_ref,
        # Mercy taps this to send the price straight into the chat she is in.
        "whatsapp_url": quote.whatsapp_url,
        "total": quote.total,
        "visit_first": quote.visit_first,
        "job": JobOut.of(jobs.get(quote.quote_ref), settings.deposit_pct, _today()),
    }


@router.get("/catalogue", dependencies=[Depends(require_pin)])
def operator_catalogue(catalogue: CatalogueDep):
    """The same chips the customer sees.

    Served from the same catalogue object the public /api/pricing uses, so the
    operator board cannot drift onto a stale price list.
    """
    return catalogue
