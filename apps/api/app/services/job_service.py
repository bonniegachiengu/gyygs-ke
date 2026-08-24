"""Job lifecycle — and the deposit gate.

PHASE_A_BUILD_BRIEF.md §2 names one rule as the most important in Phase A:

    A Job cannot enter `booked` until a deposit payment is recorded against it.

It lives HERE, in the domain service, and not in an API route or the admin UI.
That is the whole point: the calculator lane, Mercy's operator lane, and any
future client portal all go through this function, so none of them can book a
job on no money by taking a different path in.

A refusal is a normal returned outcome carrying a legible reason, not an
exception and not an HTTP error — the same convention the operator console
already uses for a refused operator call. Mercy needs to read *why*, not see a
500.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.jobs import Job, JobStatus, Payment, PaymentKind


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Outcome:
    ok: bool
    reason: str = ""
    job: Job | None = None


def ksh(cents: int) -> str:
    """Shillings, for a human-readable refusal. Mercy reads these, not logs."""
    return f"KSh {cents // 100:,}"


# ── the gate ────────────────────────────────────────────────────────────────

def book(job: Job, *, deposit_pct: int, scheduled_at: str, window: str = "") -> Outcome:
    """Move a job to `booked`. Refuses without a sufficient deposit."""
    if job.status in (JobStatus.CANCELLED, JobStatus.LOST):
        return Outcome(False, f"job {job.ref} is {job.status.value} and cannot be booked")

    if not scheduled_at:
        return Outcome(False, "a booking needs a date")

    required = job.deposit_required_cents(deposit_pct)
    paid = job.deposit_paid_cents

    if paid < required:
        short = required - paid
        return Outcome(
            False,
            f"needs {ksh(required)} deposit ({deposit_pct}%); "
            f"{ksh(paid)} recorded, {ksh(short)} short",
        )

    booked = job.model_copy(
        update={
            "status": JobStatus.BOOKED,
            "scheduled_at": f"{scheduled_at} {window}".strip(),
            "updated_at": _now(),
        }
    )
    return Outcome(True, job=booked)


# ── payments ────────────────────────────────────────────────────────────────

def record_payment(job: Job, payment: Payment) -> Outcome:
    """Append a payment. Append-only: nothing existing is ever modified.

    A duplicate `mpesa_ref` is refused here as well as at the DB level. Catching
    it in the domain means Mercy gets a sentence explaining it rather than an
    integrity error surfacing as a 500.
    """
    if payment.mpesa_ref:
        existing = {p.mpesa_ref for p in job.payments if p.mpesa_ref}
        if payment.mpesa_ref in existing:
            return Outcome(
                False,
                f"M-Pesa ref {payment.mpesa_ref} is already recorded on {job.ref}",
            )

    if payment.amount_cents <= 0 and payment.kind is not PaymentKind.WAIVER:
        return Outcome(False, "a payment must be a positive amount")

    updated = job.model_copy(
        update={"payments": [*job.payments, payment], "updated_at": _now()}
    )

    # Fully settled? Move it along and stamp the time. Deliberately does not
    # touch a job that is still only quoted -- paying in full before a booking
    # exists is unusual enough that Mercy should see it, not have the system
    # quietly advance it.
    if updated.status is JobStatus.COMPLETED and updated.balance_cents <= 0:
        updated = updated.model_copy(
            update={"status": JobStatus.PAID, "paid_at": _now()}
        )

    return Outcome(True, job=updated)


def complete(job: Job) -> Outcome:
    if job.status not in (JobStatus.BOOKED, JobStatus.IN_PROGRESS):
        return Outcome(
            False, f"only a booked job can be completed; {job.ref} is {job.status.value}"
        )
    done = job.model_copy(
        update={"status": JobStatus.COMPLETED, "completed_at": _now(), "updated_at": _now()}
    )
    # Already paid in full (deposit covered everything, or a small job settled
    # up front) -- go straight to paid rather than parking it in Unpaid.
    if done.balance_cents <= 0:
        done = done.model_copy(update={"status": JobStatus.PAID, "paid_at": _now()})
    return Outcome(True, job=done)


# ── the board ───────────────────────────────────────────────────────────────

BOARD_COLUMNS = ("new", "quoted", "booked", "today", "done", "unpaid")


def board_column(job: Job, *, today: str) -> str:
    """Which column a job appears in.

    `today` and `unpaid` are VIEWS, not statuses -- a booked job scheduled for
    today shows under Today, and a completed-but-unsettled job shows under
    Unpaid. That is what makes the board *"the business at a glance"* (§3c)
    rather than a list of database states.
    """
    if job.status in (JobStatus.COMPLETED,) and job.balance_cents > 0:
        return "unpaid"
    if job.status is JobStatus.BOOKED and job.scheduled_at.startswith(today):
        return "today"
    if job.status is JobStatus.ENQUIRY:
        return "new"
    if job.status is JobStatus.QUOTED:
        return "quoted"
    if job.status is JobStatus.BOOKED:
        return "booked"
    if job.status in (JobStatus.COMPLETED, JobStatus.PAID):
        return "done"
    return ""   # lost / cancelled are off the board
