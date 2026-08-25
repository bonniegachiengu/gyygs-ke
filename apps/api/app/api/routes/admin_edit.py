"""Editing a job after it exists — MYRAH_OPERATIONS_DESIGN.md §3b.

Scope changes are normal operations, not exceptions: a site visit exists to
discover the real scope, and *"while you're here, can you do the curtains too?"*
arrives after the job is already booked.

Two rules carry the weight here:

1. **Re-pricing goes through the same engine.** There is no endpoint that
   accepts a total. A hand-typed figure is how the board and the customer start
   disagreeing about what a job costs.
2. **Nothing is silently overwritten.** Every re-price appends a change record —
   what changed, old total, new total, when — so *"why is it more than you
   said?"* has an answer.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import CatalogueDep, SettingsDep, TransportDep
from app.api.routes.admin import JobOut, _repo, _today, require_pin
from app.domain.models import QuoteRequest
from app.domain.operator_extras import OperatorExtras, apply_operator_extras
from app.domain.pricing import compute_quote

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RepriceBody(BaseModel):
    """The new basket, in exactly the shape the calculator submits.

    `items` stays list[dict] rather than the typed QuoteItem so per-item
    operator metadata -- note, flags, tags -- survives into storage. QuoteItem
    is configured extra="ignore", so validating here would silently DROP them.
    The engine still validates its own copy; these ride alongside, untouched.
    """
    items: list[dict]
    addons: list[dict] = []
    reason: str = ""
    # Operator-only, never reachable from the customer lane.
    operator: OperatorExtras = OperatorExtras()


class NotesBody(BaseModel):
    notes: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/jobs/{ref}/reprice", dependencies=[Depends(require_pin)])
def reprice(ref: str, body: RepriceBody, catalogue: CatalogueDep, settings: SettingsDep,
            transport: TransportDep):
    """Change a job's scope and re-price it through the pricing engine."""
    repo = _repo(settings)
    job = repo.get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")
    if job.status.value in ("cancelled", "lost"):
        return {"ok": False, "reason": f"job {ref} is {job.status.value}"}

    # The SAME engine the customer's calculator uses. price_quote raises a
    # DomainError with a human sentence ("choose a size for curtains"), which
    # the app's error handler turns into a 400 carrying that message -- so the
    # operator sees what is actually wrong, not a generic failure.
    req = QuoteRequest.model_validate({
        "items": body.items,
        "addons": body.addons,
        "area": job.area or "nairobi",
        "preferred": {"day": _today(), "window": "morning"},
        "contact": {"name": job.client_name},
        "recurring": False,
    })
    # The job's own area decides the fee, so a re-price never silently drops the
    # travel Mercy is owed -- or moves it, if she has since corrected the zone.
    zone_fee = transport.fee_for(job.area or "")
    fee = body.operator.transport_override
    priced = compute_quote(req, catalogue,
                           transport=zone_fee if fee is None else fee)
    adj = apply_operator_extras(
        lines=priced.lines, subtotal=priced.subtotal, total=priced.total,
        extras=body.operator,
    )

    old_total = job.total_cents
    new_total = adj.total * 100             # engine works in whole shillings

    # `items` already holds the raw basket as JSON -- that is how the calculator
    # writes it -- so a re-price rewrites the same field in the same shape. No
    # second column, and the board's reader keeps working unchanged.
    basket = json.dumps({
        "items": body.items,
        "addons": body.addons,
        "operator": body.operator.model_dump(),
    })
    # `transport` is derived from the zone unless overridden, so the panel that
    # renders it needs the number that was actually charged.
    repo.reprice(
        ref,
        items_label=basket,
        items_json=basket,
        subtotal=adj.subtotal,
        discount=priced.discount,
        total=adj.total,
        visit_first=priced.visit_first,
    )
    # Every operator deviation names itself in the log, beside the reason.
    detail = body.reason or "scope changed"
    notes = list(adj.notes)
    if fee is not None and fee != zone_fee:
        notes.append(f"transport: KSh {zone_fee:,} → KSh {fee:,} (zone {job.area or '—'})")
    if notes:
        detail = f"{detail} · " + " · ".join(notes)
    repo.add_change(
        job_ref=ref,
        change_id=f"ch-{uuid.uuid4().hex[:12]}",
        kind="reprice",
        detail=detail,
        old_total_cents=old_total,
        new_total_cents=new_total,
        at=_now(),
    )

    updated = repo.get(ref)
    return {
        "ok": True,
        "old_total_cents": old_total,
        "new_total_cents": new_total,
        # Stated explicitly because it is the question Mercy will have: a
        # deposit already paid is never clawed back (§3b).
        "deposit_already_paid_cents": updated.deposit_paid_cents,
        "job": JobOut.of(updated, settings.deposit_pct, _today()),
    }


@router.post("/jobs/{ref}/notes", dependencies=[Depends(require_pin)])
def set_notes(ref: str, body: NotesBody, settings: SettingsDep):
    """Gate code, dog, 'start upstairs' — things Mercy currently keeps in her head."""
    repo = _repo(settings)
    job = repo.get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")
    repo.set_notes(ref, body.notes)
    repo.add_change(job_ref=ref, change_id=f"ch-{uuid.uuid4().hex[:12]}",
                    kind="notes", detail="instructions updated",
                    old_total_cents=job.total_cents, new_total_cents=job.total_cents,
                    at=_now())
    return {"ok": True, "job": JobOut.of(repo.get(ref), settings.deposit_pct, _today())}


@router.get("/jobs/{ref}/lines", dependencies=[Depends(require_pin)])
def lines(ref: str, catalogue: CatalogueDep, settings: SettingsDep,
          transport: TransportDep):
    """The engine's current line-by-line pricing for this job's basket.

    Read-only, and computed on demand rather than added to JobOut: the board
    lists many jobs at once and pricing every one of them to render a list
    nobody is reading would be wasteful. The edit form asks for exactly the one
    job it is about to change.

    This is what makes a price override honest -- Mercy sees the auto price and
    the label the engine gave it, and adjusts THAT, rather than typing a total
    over the top of a number she cannot see.
    """
    repo = _repo(settings)
    job = repo.get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")
    try:
        basket = json.loads(job.items or "{}")
    except ValueError:
        basket = {}
    req = QuoteRequest.model_validate({
        "items": basket.get("items", []),
        "addons": basket.get("addons", []),
        "area": job.area or "nairobi",
        "preferred": {"day": _today(), "window": "morning"},
        "contact": {"name": job.client_name},
        "recurring": False,
    })
    priced = compute_quote(req, catalogue, transport=transport.fee_for(job.area or ""))
    saved = (basket.get("operator") or {})
    return {
        "lines": [{"label": l.label, "amount": l.amount} for l in priced.lines],
        "subtotal": priced.subtotal,
        "total": priced.total,
        "transport": priced.transport,
        "transport_zone_fee": transport.fee_for(job.area or ""),
        "area": job.area or "",
        # Whatever deviations are already on the job, so the form opens showing
        # them rather than silently discarding them on the next save.
        "operator": {
            "custom_lines": saved.get("custom_lines", []),
            "overrides": saved.get("overrides", []),
        },
    }


@router.get("/jobs/{ref}/changes", dependencies=[Depends(require_pin)])
def changes(ref: str, settings: SettingsDep):
    repo = _repo(settings)
    if not repo.get(ref):
        raise HTTPException(404, f"no job {ref}")
    return {"changes": repo.changes_for(ref)}
