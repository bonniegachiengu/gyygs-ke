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

from app.api.deps import CatalogueDep, SettingsDep
from app.api.routes.admin import JobOut, _repo, _today, require_pin
from app.domain.models import QuoteRequest
from app.domain.pricing import compute_quote

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RepriceBody(BaseModel):
    """The new basket, in exactly the shape the calculator submits."""
    items: list[dict]
    addons: list[dict] = []
    reason: str = ""


class NotesBody(BaseModel):
    notes: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/jobs/{ref}/reprice", dependencies=[Depends(require_pin)])
def reprice(ref: str, body: RepriceBody, catalogue: CatalogueDep, settings: SettingsDep):
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
    priced = compute_quote(req, catalogue)

    old_total = job.total_cents
    new_total = priced.total * 100          # engine works in whole shillings

    # `items` already holds the raw basket as JSON -- that is how the calculator
    # writes it -- so a re-price rewrites the same field in the same shape. No
    # second column, and the board's reader keeps working unchanged.
    repo.reprice(
        ref,
        items_label=json.dumps({"items": body.items, "addons": body.addons}),
        items_json=json.dumps({"items": body.items, "addons": body.addons}),
        subtotal=priced.subtotal,
        discount=priced.discount,
        total=priced.total,
        visit_first=priced.visit_first,
    )
    repo.add_change(
        job_ref=ref,
        change_id=f"ch-{uuid.uuid4().hex[:12]}",
        kind="reprice",
        detail=body.reason or "scope changed",
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


@router.get("/jobs/{ref}/changes", dependencies=[Depends(require_pin)])
def changes(ref: str, settings: SettingsDep):
    repo = _repo(settings)
    if not repo.get(ref):
        raise HTTPException(404, f"no job {ref}")
    return {"changes": repo.changes_for(ref)}
