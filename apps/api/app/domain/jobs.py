"""The Job spine — Phase A.

`MYRAH_OPERATIONS_DESIGN.md` §1: *"almost every module a service business thinks
it needs is a different view of the same event."* Everything references a Job.

Two rules here are load-bearing and deliberately not negotiable in code:

1. **Money is integer minor units.** No float goes near an amount, anywhere.
2. **`paid` is DERIVED, never stored.** A job's paid total is a fold over its
   payments. There is no mutable `paid_cents` column that can drift from the
   ledger, so the board and the money can never disagree.

Payments are append-only: a correction is a reversing entry, never an edit
(ops design §8, same discipline as 365+).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

Cents = int


class JobStatus(str, Enum):
    """`MYRAH_WHATSAPP_AND_CMS.md` §3a, verbatim."""

    ENQUIRY = "enquiry"
    QUOTED = "quoted"
    BOOKED = "booked"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAID = "paid"
    LOST = "lost"
    CANCELLED = "cancelled"


class JobSource(str, Enum):
    """Which lane the job arrived through (§3b). Both feed the same spine."""

    CALCULATOR = "calculator"   # customer self-served
    OPERATOR = "operator"       # Mercy raised it from a chat


class PaymentKind(str, Enum):
    DEPOSIT = "deposit"
    BALANCE = "balance"
    # A refund is recorded as its own negative-effect entry rather than by
    # deleting the original, so the history stays readable.
    REFUND = "refund"
    # Mercy forgiving a forfeited deposit as goodwill. Recorded explicitly so a
    # waiver is visible in the ledger instead of looking like money that
    # arrived (PHASE_A_BUILD_BRIEF.md §2).
    WAIVER = "waiver"


class PaymentMethod(str, Enum):
    MPESA = "mpesa"
    CASH = "cash"
    BANK = "bank"
    NONE = "none"   # for waivers, where no money moved


class Client(BaseModel):
    """One per person. Jobs hang off it — which is what makes repeat business
    and follow-ups possible at all (§3b)."""

    id: str
    name: str
    phone: str | None = None
    area: str = ""
    estate: str = ""
    notes: str = ""
    created_at: datetime


class Payment(BaseModel):
    id: str
    job_ref: str
    amount_cents: Cents
    kind: PaymentKind
    method: PaymentMethod = PaymentMethod.MPESA
    # UNIQUE where not null, enforced at the DB level — the duplicate-payment
    # defence. Two people recording the same M-Pesa transfer is a real thing.
    mpesa_ref: str | None = None
    recorded_by: str = "mercy"
    recorded_at: datetime
    note: str = ""

    @property
    def signed_cents(self) -> Cents:
        """What this entry contributes to the amount actually received.

        A refund reduces it. A waiver contributes NOTHING — it forgives a debt
        rather than paying it, and counting it as money received would overstate
        what is in Pochi.
        """
        if self.kind is PaymentKind.REFUND:
            return -abs(self.amount_cents)
        if self.kind is PaymentKind.WAIVER:
            return 0
        return self.amount_cents


class Job(BaseModel):
    """The spine. `ref` is the existing MY-YYMMDD-nnn quote reference, kept as
    the human-facing identity so a ref Mercy already quoted stays valid."""

    ref: str
    client_id: str
    client_name: str
    items: str = ""                 # itemised quote lines, as stored today
    subtotal_cents: Cents = 0
    discount_cents: Cents = 0
    total_cents: Cents = 0
    # No hard total — priced after a look. Such a job cannot compute a
    # meaningful deposit, so the gate treats it separately (see below).
    visit_first: bool = False
    status: JobStatus = JobStatus.QUOTED
    source: JobSource = JobSource.CALCULATOR
    area: str = ""
    estate: str = ""
    preferred: str = ""             # what the customer asked for
    scheduled_at: str = ""          # what was actually agreed, set at booking
    completed_at: datetime | None = None
    paid_at: datetime | None = None
    receipt_ref: str = ""
    created_at: datetime
    updated_at: datetime
    payments: list[Payment] = Field(default_factory=list)

    # ── derived money — never stored ────────────────────────────────────────

    @property
    def paid_cents(self) -> Cents:
        """Folded from payments. There is no column for this."""
        return sum(p.signed_cents for p in self.payments)

    @property
    def deposit_paid_cents(self) -> Cents:
        return sum(
            p.signed_cents for p in self.payments if p.kind is PaymentKind.DEPOSIT
        )

    @property
    def balance_cents(self) -> Cents:
        return self.total_cents - self.paid_cents

    def deposit_required_cents(self, pct: int) -> Cents:
        """30% by default, from config — Mercy can change the number without a
        code change (§11 decision 1).

        Rounded DOWN so the system never asks for more than the stated
        percentage; a shilling in the customer's favour is the right direction
        for a rounding error to go.
        """
        if self.visit_first:
            return 0
        return (self.total_cents * pct) // 100

    def deposit_satisfied(self, pct: int) -> bool:
        # A waiver contributes 0 to signed_cents, so a waived deposit does NOT
        # satisfy the gate by itself. Mercy waiving a forfeit is not the same as
        # a client paying to hold a slot, and conflating them would let a job be
        # booked on no money at all.
        return self.deposit_paid_cents >= self.deposit_required_cents(pct)
