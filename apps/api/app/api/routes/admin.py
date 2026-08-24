"""Mercy's operator surface — /api/admin/*.

These routes are deliberately THIN. Every decision that matters -- above all the
deposit gate -- lives in app/services/job_service.py, so the calculator lane,
this operator lane and any future client portal all inherit it. A route that
re-implemented the gate would be a second way to book a job on no money.

A refused action returns HTTP 200 with `{"ok": false, "reason": "..."}`. That is
the house convention (the operator console already works this way) and it is the
right one here: a refusal is an expected business outcome Mercy needs to READ --
"KSh 640 short" -- not an error page.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CatalogueDep, SettingsDep
from app.domain.jobs import Job, JobSource, JobStatus, Payment, PaymentKind, PaymentMethod
from app.services import job_service
from app.services.job_service import board_column

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── auth ────────────────────────────────────────────────────────────────────
# A shared PIN, exactly as MYRAH_WHATSAPP_AND_CMS.md §3d says to start:
# "start with a shared PIN; proper auth later". Said plainly rather than
# pretended otherwise -- this is one operator on one phone today.

def require_pin(settings: SettingsDep, x_admin_pin: str = Header(default="")) -> None:
    expected = settings.admin_pin
    if not expected:
        raise HTTPException(503, "admin surface is not configured (ADMIN_PIN unset)")
    if x_admin_pin != expected:
        raise HTTPException(401, "bad or missing PIN")


def _repo(settings: SettingsDep):
    from app.repositories.jobs_sqlite import SqliteJobRepository
    return SqliteJobRepository(settings.lead_db_path)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().date().isoformat()


# ── wire shapes ─────────────────────────────────────────────────────────────

class JobOut(BaseModel):
    ref: str
    client_id: str
    client_name: str
    items: str
    total_cents: int
    visit_first: bool
    status: str
    source: str
    area: str
    preferred: str
    scheduled_at: str
    column: str
    # Derived, every time, from the payment ledger -- never stored.
    paid_cents: int
    balance_cents: int
    deposit_required_cents: int
    deposit_paid_cents: int
    deposit_satisfied: bool
    receipt_ref: str
    payments: list[dict]

    @classmethod
    def of(cls, job: Job, pct: int, today: str) -> "JobOut":
        return cls(
            ref=job.ref, client_id=job.client_id, client_name=job.client_name,
            items=job.items, total_cents=job.total_cents, visit_first=job.visit_first,
            status=job.status.value, source=job.source.value, area=job.area,
            preferred=job.preferred, scheduled_at=job.scheduled_at,
            column=board_column(job, today=today),
            paid_cents=job.paid_cents, balance_cents=job.balance_cents,
            deposit_required_cents=job.deposit_required_cents(pct),
            deposit_paid_cents=job.deposit_paid_cents,
            deposit_satisfied=job.deposit_satisfied(pct),
            receipt_ref=job.receipt_ref,
            payments=[
                {"id": p.id, "amount_cents": p.amount_cents, "kind": p.kind.value,
                 "method": p.method.value, "mpesa_ref": p.mpesa_ref,
                 "recorded_at": p.recorded_at.isoformat(), "note": p.note}
                for p in job.payments
            ],
        )


class BookBody(BaseModel):
    scheduled_at: str = Field(..., description="YYYY-MM-DD")
    window: str = ""


class PaymentBody(BaseModel):
    amount_cents: int
    kind: PaymentKind = PaymentKind.DEPOSIT
    method: PaymentMethod = PaymentMethod.MPESA
    mpesa_ref: str | None = None
    note: str = ""


# ── the board ───────────────────────────────────────────────────────────────

@router.get("/board", dependencies=[Depends(require_pin)])
def board(settings: SettingsDep):
    """Every job, grouped into the six columns. One call = the whole business."""
    repo = _repo(settings)
    today = _today()
    pct = settings.deposit_pct
    cols: dict[str, list] = {c: [] for c in job_service.BOARD_COLUMNS}
    for job in repo.list():
        out = JobOut.of(job, pct, today)
        if out.column:                      # lost/cancelled are off the board
            cols[out.column].append(out)
    return {"columns": cols, "today": today, "deposit_pct": pct}


@router.get("/jobs/{ref}", dependencies=[Depends(require_pin)])
def get_job(ref: str, settings: SettingsDep):
    job = _repo(settings).get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")
    return JobOut.of(job, settings.deposit_pct, _today())


@router.post("/jobs/{ref}/book", dependencies=[Depends(require_pin)])
def book_job(ref: str, body: BookBody, settings: SettingsDep):
    """★ The deposit gate. The route does not decide -- job_service.book does."""
    repo = _repo(settings)
    job = repo.get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")

    out = job_service.book(
        job, deposit_pct=settings.deposit_pct,
        scheduled_at=body.scheduled_at, window=body.window,
    )
    if not out.ok:
        # 200 with a legible reason, not an error page: Mercy reads this.
        return {"ok": False, "reason": out.reason,
                "job": JobOut.of(job, settings.deposit_pct, _today())}
    repo.save(out.job)
    return {"ok": True, "job": JobOut.of(out.job, settings.deposit_pct, _today())}


@router.post("/jobs/{ref}/payments", dependencies=[Depends(require_pin)])
def add_payment(ref: str, body: PaymentBody, settings: SettingsDep):
    repo = _repo(settings)
    job = repo.get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")

    payment = Payment(
        id=f"pm-{uuid.uuid4().hex[:12]}", job_ref=ref,
        amount_cents=body.amount_cents, kind=body.kind, method=body.method,
        mpesa_ref=body.mpesa_ref or None, recorded_at=_now(), note=body.note,
    )
    out = job_service.record_payment(job, payment)
    if not out.ok:
        return {"ok": False, "reason": out.reason,
                "job": JobOut.of(job, settings.deposit_pct, _today())}

    repo.add_payment(payment)
    repo.save(out.job)
    return {"ok": True, "job": JobOut.of(repo.get(ref), settings.deposit_pct, _today())}


@router.post("/jobs/{ref}/complete", dependencies=[Depends(require_pin)])
def complete_job(ref: str, settings: SettingsDep):
    repo = _repo(settings)
    job = repo.get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")
    out = job_service.complete(job)
    if not out.ok:
        return {"ok": False, "reason": out.reason,
                "job": JobOut.of(job, settings.deposit_pct, _today())}
    repo.save(out.job)
    return {"ok": True, "job": JobOut.of(out.job, settings.deposit_pct, _today())}


@router.get("/jobs/{ref}/receipt", dependencies=[Depends(require_pin)])
def receipt(ref: str, settings: SettingsDep):
    """A Myrah receipt from day one (ops design §5c).

    eTIMS stays config-stubbed until the KRA PIN exists -- the fields render
    "pending registration" rather than inventing a tax number.
    """
    repo = _repo(settings)
    job = repo.get(ref)
    if not job:
        raise HTTPException(404, f"no job {ref}")
    return {
        "business": {
            "name": "Myrah Cleaning Services",
            "legal_name": settings.business_legal_name,
            "kra_pin": settings.business_kra_pin,
            "vat_registered": settings.vat_registered,
            "etims": "enabled" if settings.etims_enabled else "pending registration",
        },
        "receipt_ref": job.receipt_ref or f"RC-{job.ref}",
        "job_ref": job.ref,
        "client": job.client_name,
        "area": job.area,
        "items": job.items,
        "total_cents": job.total_cents,
        "paid_cents": job.paid_cents,
        "balance_cents": job.balance_cents,
        "payments": [
            {"kind": p.kind.value, "amount_cents": p.amount_cents,
             "method": p.method.value, "mpesa_ref": p.mpesa_ref,
             "at": p.recorded_at.isoformat()} for p in job.payments
        ],
        "issued_at": _now().isoformat(),
    }


@router.get("/clients/{client_id}", dependencies=[Depends(require_pin)])
def client(client_id: str, settings: SettingsDep):
    repo = _repo(settings)
    c = repo.get_client(client_id)
    if not c:
        raise HTTPException(404, "no such client")
    jobs = [j for j in repo.list() if j.client_id == client_id]
    return {
        "client": c.model_dump(mode="json"),
        "job_count": len(jobs),
        "lifetime_cents": sum(j.paid_cents for j in jobs),
        "jobs": [JobOut.of(j, settings.deposit_pct, _today()) for j in jobs],
    }
