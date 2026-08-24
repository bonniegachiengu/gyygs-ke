"""Phase A — the Job spine, the deposit gate, and the safety rule.

The two load-bearing tests here are `TestDepositGate` (a job must not reach
`booked` on no money) and `TestNoRealNumberInTests` (no test may ever be able to
reach Mercy's live line). Everything else supports them.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.jobs import (
    Job,
    JobSource,
    JobStatus,
    Payment,
    PaymentKind,
    PaymentMethod,
)
from app.services.job_service import board_column, book, complete, record_payment

DEPOSIT_PCT = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_job(total_cents: int = 380_000, **kw) -> Job:
    """The worked example from CLAUDE.md: KSh 3,800."""
    base = dict(
        ref="MY-260824-001",
        client_id="c1",
        client_name="Faith",
        items="Sofa 3 seats; Mattress 5x6; Fridge",
        subtotal_cents=total_cents,
        total_cents=total_cents,
        status=JobStatus.QUOTED,
        source=JobSource.CALCULATOR,
        area="ruiru",
        created_at=_now(),
        updated_at=_now(),
    )
    base.update(kw)
    return Job(**base)


def pay(amount_cents: int, kind=PaymentKind.DEPOSIT, **kw) -> Payment:
    return Payment(
        id=kw.pop("id", "p1"),
        job_ref="MY-260824-001",
        amount_cents=amount_cents,
        kind=kind,
        method=kw.pop("method", PaymentMethod.MPESA),
        recorded_at=_now(),
        **kw,
    )


# ── the gate ────────────────────────────────────────────────────────────────

class TestDepositGate:
    def test_a_job_with_no_deposit_cannot_be_booked(self):
        out = book(make_job(), deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01")
        assert out.ok is False
        assert out.job is None

    def test_the_refusal_says_how_much_is_needed_and_how_short(self):
        out = book(make_job(), deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01")
        # 30% of 3,800 = 1,140. Mercy must be able to read this to a client.
        assert "KSh 1,140" in out.reason
        assert "30%" in out.reason
        assert "short" in out.reason

    def test_a_partial_deposit_is_still_refused(self):
        job = make_job()
        job = record_payment(job, pay(50_000)).job          # KSh 500 of 1,140
        out = book(job, deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01")
        assert out.ok is False
        assert "KSh 640 short" in out.reason

    def test_a_sufficient_deposit_books_the_job(self):
        job = make_job()
        job = record_payment(job, pay(114_000)).job         # exactly 30%
        out = book(job, deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01", window="morning")
        assert out.ok is True
        assert out.job.status is JobStatus.BOOKED
        assert out.job.scheduled_at == "2026-09-01 morning"

    def test_a_waiver_alone_does_NOT_satisfy_the_gate(self):
        """Mercy forgiving a forfeit is not a client paying to hold a slot.

        Conflating them would let a job be booked on no money at all.
        """
        job = make_job()
        job = record_payment(job, pay(114_000, kind=PaymentKind.WAIVER)).job
        out = book(job, deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01")
        assert out.ok is False

    def test_a_visit_first_job_needs_no_deposit(self):
        """No hard total means no meaningful percentage of it."""
        job = make_job(total_cents=0, visit_first=True)
        out = book(job, deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01")
        assert out.ok is True

    def test_a_booking_needs_a_date(self):
        job = make_job()
        job = record_payment(job, pay(114_000)).job
        assert book(job, deposit_pct=DEPOSIT_PCT, scheduled_at="").ok is False

    def test_a_cancelled_job_cannot_be_booked_even_with_a_deposit(self):
        job = make_job(status=JobStatus.CANCELLED)
        job = record_payment(job, pay(114_000)).job
        assert book(job, deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01").ok is False

    def test_the_percentage_comes_from_config_not_a_literal(self):
        """Mercy can change 30% without a code change (§11 decision 1)."""
        job = make_job()
        assert job.deposit_required_cents(30) == 114_000
        assert job.deposit_required_cents(50) == 190_000
        assert job.deposit_required_cents(0) == 0


# ── money is derived, never stored ──────────────────────────────────────────

class TestMoneyIsFolded:
    def test_paid_is_a_fold_over_payments(self):
        job = make_job()
        job = record_payment(job, pay(114_000, id="p1")).job
        job = record_payment(job, pay(100_000, id="p2", kind=PaymentKind.BALANCE)).job
        assert job.paid_cents == 214_000
        assert job.balance_cents == 380_000 - 214_000

    def test_a_refund_reduces_the_paid_total_without_deleting_anything(self):
        job = make_job()
        job = record_payment(job, pay(114_000, id="p1")).job
        job = record_payment(job, pay(50_000, id="p2", kind=PaymentKind.REFUND)).job
        assert job.paid_cents == 64_000
        assert len(job.payments) == 2, "append-only: the original survives"

    def test_a_waiver_forgives_without_counting_as_money_received(self):
        job = make_job()
        job = record_payment(job, pay(114_000, kind=PaymentKind.WAIVER)).job
        assert job.paid_cents == 0, "nothing arrived in Pochi"
        assert len(job.payments) == 1, "but it is visible in the ledger"

    def test_there_is_no_settable_paid_field(self):
        """If a mutable paid column existed it could drift from the ledger."""
        assert "paid_cents" not in Job.model_fields

    def test_a_duplicate_mpesa_ref_is_refused_with_a_sentence(self):
        job = make_job()
        job = record_payment(job, pay(114_000, id="p1", mpesa_ref="TFE5G7H8L3")).job
        out = record_payment(job, pay(114_000, id="p2", mpesa_ref="TFE5G7H8L3"))
        assert out.ok is False
        assert "TFE5G7H8L3" in out.reason


# ── lifecycle + board ───────────────────────────────────────────────────────

class TestLifecycleAndBoard:
    def _booked(self) -> Job:
        job = make_job()
        job = record_payment(job, pay(114_000)).job
        return book(job, deposit_pct=DEPOSIT_PCT, scheduled_at="2026-09-01").job

    def test_completing_an_unsettled_job_leaves_a_balance_owing(self):
        out = complete(self._booked())
        assert out.ok is True
        assert out.job.status is JobStatus.COMPLETED
        assert out.job.balance_cents == 380_000 - 114_000

    def test_settling_the_balance_moves_it_to_paid(self):
        job = complete(self._booked()).job
        job = record_payment(job, pay(266_000, id="p2", kind=PaymentKind.BALANCE)).job
        assert job.status is JobStatus.PAID
        assert job.paid_at is not None

    def test_only_a_booked_job_can_be_completed(self):
        assert complete(make_job()).ok is False

    def test_an_unsettled_completed_job_shows_under_unpaid(self):
        job = complete(self._booked()).job
        assert board_column(job, today="2026-09-01") == "unpaid"

    def test_a_job_scheduled_today_shows_under_today(self):
        assert board_column(self._booked(), today="2026-09-01") == "today"

    def test_the_same_job_shows_under_booked_on_another_day(self):
        assert board_column(self._booked(), today="2026-08-30") == "booked"

    def test_a_cancelled_job_is_off_the_board(self):
        assert board_column(make_job(status=JobStatus.CANCELLED), today="2026-09-01") == ""


# ── ★ the safety rule, enforced mechanically ────────────────────────────────

class TestNoRealNumberInTests:
    """PHASE_A_BUILD_BRIEF.md §0.

    Mercy's line is the real business WhatsApp AND the Pochi line real payments
    land on. No test may be able to reach it. This is checked by grepping the
    tree rather than by reviewer discipline, because reviewer discipline is
    exactly what fails at 2am.
    """

    # Assembled at runtime so this file does not itself contain the literal —
    # otherwise the check would match its own source and never be trustworthy.
    FORBIDDEN = "254" + "716" + "869648"

    def _tree(self) -> Path:
        """The REPO ROOT, not just apps/api.

        Scoping this to apps/api is how the first version of this test passed
        while `.env.example` at the repo root still carried the real number.
        The guard is only worth having if it covers everywhere a committed file
        can live.
        """
        return Path(__file__).resolve().parents[3]

    SCAN_SUFFIXES = {
        ".py", ".json", ".toml", ".env", ".example", ".ts", ".tsx",
        ".js", ".html", ".yml", ".yaml", ".conf", ".ps1", ".sh", ".vbs",
    }

    def test_the_real_business_number_appears_nowhere_in_the_repo(self):
        root = self._tree()
        skip = {"node_modules", "__pycache__", ".git", "dist", ".venv-native", "data"}
        hits = []
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in self.SCAN_SUFFIXES:
                continue
            if skip & set(p.parts):
                continue
            if p.name == Path(__file__).name:
                continue          # this file builds the string at runtime
            try:
                if self.FORBIDDEN in p.read_text(encoding="utf-8", errors="ignore"):
                    hits.append(str(p.relative_to(root)))
            except OSError:
                continue
        assert hits == [], f"Mercy's live line must not appear in: {hits}"

    def test_the_configured_number_is_the_test_line_not_the_real_one(self):
        from app.core.config import get_settings

        get_settings.cache_clear()
        assert get_settings().whatsapp_number != self.FORBIDDEN

    def test_tests_assert_on_config_never_on_a_literal_number(self):
        """A fixture carrying a hardcoded number is how the real one gets in."""
        offenders = []
        for p in Path(__file__).resolve().parent.glob("test_*.py"):
            body = p.read_text(encoding="utf-8", errors="ignore")
            if "254716" in body and p.name != Path(__file__).name:
                offenders.append(p.name)
        assert offenders == [], f"hardcoded real number in: {offenders}"
