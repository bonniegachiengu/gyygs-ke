"""The LeadRepository -> JobRepository migration.

PHASE_A_BUILD_BRIEF.md §9 requires one thing above all here: *"Every existing
lead migrated to quoted/calculator, counts and totals unchanged -- proven by
test."*

Mercy's leads table is the only record of what the business has quoted. A
migration that loses or alters a row is worse than no migration.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.jobs import Job, JobSource, JobStatus, Payment, PaymentKind, PaymentMethod
from app.repositories.base import Lead
from app.repositories.jobs_sqlite import SqliteJobRepository
from app.repositories.sqlite import SqliteLeadRepository


def _now():
    return datetime.now(timezone.utc)


def seed_leads(db: str, n: int = 3) -> list[Lead]:
    """Write leads through the EXISTING store, exactly as production has."""
    repo = SqliteLeadRepository(db)
    leads = []
    for i in range(1, n + 1):
        lead = Lead(
            ref=f"MY-260824-{i:03d}",
            timestamp=_now(),
            name=f"Client {i}",
            phone=f"25472200000{i}",
            items=f"Sofa {i} seats",
            subtotal=i * 50_000,
            discount=0,
            total=i * 50_000,
            area="ruiru",
            preferred="2026-09-01 morning",
            visit_first=False,
            sent_to_wa=True,
        )
        repo.append(lead)
        leads.append(lead)
    return leads


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "leads.db")


class TestMigrationPreservesHistory:
    def test_every_existing_lead_survives_as_a_job(self, db):
        seeded = seed_leads(db, 3)
        jobs = SqliteJobRepository(db).list()
        assert len(jobs) == len(seeded), "no lead may be lost"
        assert {j.ref for j in jobs} == {l.ref for l in seeded}

    def test_totals_are_unchanged_to_the_cent(self, db):
        """The leads table is in whole SHILLINGS; the Job spine is in CENTS.

        The value must be identical in real money -- only the unit changes, at
        the one repository boundary where the two systems meet.
        """
        seeded = seed_leads(db, 4)
        jobs = SqliteJobRepository(db).list()
        K = 100
        assert sum(j.total_cents for j in jobs) == sum(l.total for l in seeded) * K
        for j in jobs:
            src = next(l for l in seeded if l.ref == j.ref)
            assert (j.subtotal_cents, j.discount_cents, j.total_cents) == (
                src.subtotal * K, src.discount * K, src.total * K
            )

    def test_a_real_worked_example_asks_for_the_right_deposit(self, db):
        """Regression for the unit bug found end-to-end on staging: a KSh 3,800
        job asked for a 'KSh 11 deposit' because shillings were read as cents."""
        repo = SqliteJobRepository(db)
        SqliteLeadRepository(db).append(Lead(
            ref="MY-260824-777", timestamp=_now(), name="Worked Example",
            phone=None, items="Sofa 3 seats; Mattress 5x6; Fridge",
            subtotal=3800, discount=0, total=3800, area="ruiru",
            preferred="", visit_first=False, sent_to_wa=False,
        ))
        job = SqliteJobRepository(db).get("MY-260824-777")
        assert job.total_cents == 380_000, "KSh 3,800"
        assert job.deposit_required_cents(30) == 114_000, "KSh 1,140, not KSh 11"

    def test_migrated_leads_land_on_quoted_calculator(self, db):
        """A lead from the calculator that nobody has acted on IS a quoted job."""
        seed_leads(db, 2)
        for j in SqliteJobRepository(db).list():
            assert j.status is JobStatus.QUOTED
            assert j.source is JobSource.CALCULATOR

    def test_customer_details_survive(self, db):
        seeded = seed_leads(db, 1)
        j = SqliteJobRepository(db).list()[0]
        assert (j.client_name, j.area, j.preferred) == (
            seeded[0].name, seeded[0].area, seeded[0].preferred
        )

    def test_a_client_record_is_created_per_person(self, db):
        seed_leads(db, 3)
        repo = SqliteJobRepository(db)
        for j in repo.list():
            assert j.client_id, "every job must hang off a client"
            assert repo.get_client(j.client_id) is not None

    def test_migration_is_idempotent(self, db):
        seed_leads(db, 3)
        first = SqliteJobRepository(db).list()
        second = SqliteJobRepository(db).list()   # constructor migrates again
        third = SqliteJobRepository(db).list()
        assert len(first) == len(second) == len(third) == 3
        assert {j.client_id for j in second} == {j.client_id for j in third}

    def test_the_lead_store_still_works_after_migration(self, db):
        """Additive means additive: the old reader must not break."""
        seed_leads(db, 2)
        SqliteJobRepository(db)                      # migrate
        assert len(SqliteLeadRepository(db).list()) == 2

    def test_a_new_lead_written_after_migration_is_visible_as_a_job(self, db):
        seed_leads(db, 1)
        SqliteJobRepository(db)
        SqliteLeadRepository(db).append(
            Lead(ref="MY-260824-099", timestamp=_now(), name="Late Arrival",
                 phone=None, items="Carpet", subtotal=70_000, discount=0,
                 total=70_000, area="thika", preferred="", visit_first=False,
                 sent_to_wa=False)
        )
        refs = {j.ref for j in SqliteJobRepository(db).list()}
        assert "MY-260824-099" in refs


class TestPaymentsArePersistedAppendOnly:
    @pytest.fixture(autouse=True)
    def _seeded(self, db):
        """Every test here needs a job to attach payments to."""
        seed_leads(db, 1)

    def test_a_payment_round_trips_and_folds(self, db):
        repo = SqliteJobRepository(db)
        job = repo.list()[0]
        repo.add_payment(Payment(
            id="p1", job_ref=job.ref, amount_cents=15_000,
            kind=PaymentKind.DEPOSIT, method=PaymentMethod.MPESA,
            mpesa_ref="TFE5G7H8L3", recorded_at=_now(),
        ))
        reloaded = repo.get(job.ref)
        assert len(reloaded.payments) == 1
        assert reloaded.paid_cents == 15_000

    def test_the_database_itself_rejects_a_duplicate_mpesa_ref(self, db):
        """Defence in depth: the domain refuses it, and so does the schema."""
        import sqlite3
        repo = SqliteJobRepository(db)
        job = repo.list()[0]
        p = Payment(id="p1", job_ref=job.ref, amount_cents=15_000,
                    kind=PaymentKind.DEPOSIT, mpesa_ref="DUP123", recorded_at=_now())
        repo.add_payment(p)
        with pytest.raises(sqlite3.IntegrityError):
            repo.add_payment(p.model_copy(update={"id": "p2"}))

    def test_two_payments_with_no_mpesa_ref_are_both_allowed(self, db):
        """UNIQUE ... WHERE mpesa_ref IS NOT NULL -- cash has no ref."""
        repo = SqliteJobRepository(db)
        job = repo.list()[0]
        for i in (1, 2):
            repo.add_payment(Payment(
                id=f"p{i}", job_ref=job.ref, amount_cents=5_000,
                kind=PaymentKind.BALANCE, method=PaymentMethod.CASH,
                recorded_at=_now(),
            ))
        assert len(repo.get(job.ref).payments) == 2

    def test_saving_a_job_never_rewrites_payment_history(self, db):
        repo = SqliteJobRepository(db)
        job = repo.list()[0]
        repo.add_payment(Payment(id="p1", job_ref=job.ref, amount_cents=15_000,
                                 kind=PaymentKind.DEPOSIT, recorded_at=_now()))
        job = repo.get(job.ref)
        repo.save(job.model_copy(update={"status": JobStatus.BOOKED, "payments": []}))
        assert len(repo.get(job.ref).payments) == 1, "payments are append-only"
