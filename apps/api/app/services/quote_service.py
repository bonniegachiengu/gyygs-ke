"""Quote orchestration — the impure shell around the pure engine.

Allocate a reference, recompute the price authoritatively, build the WhatsApp
handoff, log the lead. The engine itself stays free of clocks and storage.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from app.domain.models import PricingCatalogue, QuoteRequest, QuoteResponse
from app.domain.pricing import ETIMS_NOTE, TRANSPORT_NOTE, compute_quote
from app.domain.whatsapp import build_handoff, build_message
from app.repositories.base import Lead, LeadRepository
from app.services.ref_service import QuoteRefAllocator


def _area(cat: PricingCatalogue, key: str):
    return next((a for a in cat.areas if a.key == key), None)


def _preferred_cell(req: QuoteRequest) -> str:
    if req.preferred is None:
        return ""
    parts = [
        req.preferred.day.isoformat() if req.preferred.day else "",
        req.preferred.window or "",
    ]
    return " ".join(p for p in parts if p)


def create_quote(
    req: QuoteRequest,
    *,
    cat: PricingCatalogue,
    repo: LeadRepository,
    refs: QuoteRefAllocator,
    whatsapp_number: str,
    site_host: str,
    vat_registered: bool = False,
    vat_rate: int = 16,
    now: datetime | None = None,
) -> QuoteResponse:
    now = now or datetime.now(UTC)

    # Recompute from the request's SELECTIONS. Any total the client sent was
    # dropped at the schema boundary (QuoteRequest uses extra="ignore").
    #
    # repeat_customer is hard-false in v1: there is no customer record, so every
    # quote is priced as a first job. req.recurring is intent only — it never
    # discounts. Booking (Phase 3) is what will set this.
    comp = compute_quote(
        req,
        cat,
        vat_registered=vat_registered,
        vat_rate=vat_rate,
        repeat_customer=False,
    )

    quote_ref = refs.next_ref(now)
    area = _area(cat, req.area)
    area_label = area.label if area else req.area
    etims_note = ETIMS_NOTE if req.business_name else None

    text = build_message(
        lines=comp.lines,
        total=comp.total,
        quote_ref=quote_ref,
        area_label=area_label,
        site_host=site_host,
        visit_first=comp.visit_first,
        preferred=req.preferred,
        contact_name=req.contact.name,
        discount=comp.discount,
        discount_pct=cat.rules.recurring_discount_pct,
        minimum_adjustment=comp.minimum_adjustment,
        minimum_callout=cat.minimum_callout,
        vat=comp.vat,
        vat_rate=vat_rate,
        area_needs_coverage_check=bool(area and area.visit),
        recurring=req.recurring,
        recurring_discount_pct=cat.rules.recurring_discount_pct,
        business_name=req.business_name,
        kra_pin=req.kra_pin,
        etims_note=etims_note,
    )
    whatsapp_url = build_handoff(text, whatsapp_number, line_count=len(comp.lines))

    # Logged with sent_to_wa=False so drop-off is visible (SPEC §8); the beacon
    # on the Send button flips it.
    repo.append(
        Lead(
            ref=quote_ref,
            timestamp=now,
            name=req.contact.name,
            phone=req.contact.phone,
            items=json.dumps(
                {
                    "items": [i.model_dump(exclude_defaults=True) for i in req.items],
                    "addons": [a.model_dump() for a in req.addons],
                    "recurring": req.recurring,
                    "site_visit": req.site_visit.model_dump() if req.site_visit else None,
                },
                default=str,
            ),
            subtotal=comp.subtotal,
            discount=comp.discount,
            total=comp.total,
            area=req.area,
            preferred=_preferred_cell(req),
            visit_first=comp.visit_first,
            sent_to_wa=False,
            lead_id=str(uuid.uuid4()),
        )
    )

    return QuoteResponse(
        quote_ref=quote_ref,
        currency=cat.currency,
        lines=comp.lines,
        subtotal=comp.subtotal,
        discount=comp.discount,
        total=comp.total,
        visit_first=comp.visit_first,
        transport_note=TRANSPORT_NOTE,
        whatsapp_url=whatsapp_url,
        created_at=now,
        vat=comp.vat or None,
        etims_note=etims_note,
    )
