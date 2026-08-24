"""JobRepository on SQLite — the LeadRepository seam, generalised.

`MYRAH_WHATSAPP_AND_CMS.md` §3b: *"The calculator's LeadRepository generalises
to a JobRepository. Same seam, more fields."* -- and explicitly **"no rewrite"**.

So this does not replace the leads table; it GROWS it. Additive columns plus two
new tables. Every lead Mercy already has becomes a Job at `quoted/calculator`,
preserved, because her history is the only record of what the business has done.

Payments live in their own table and are append-only. A job's paid total is
folded from them on read -- there is no paid column, so the board and the money
cannot drift apart.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.domain.jobs import (
    Client,
    Job,
    JobSource,
    JobStatus,
    Payment,
    PaymentKind,
    PaymentMethod,
)

# Columns added to the existing `leads` table. Additive only -- nothing is
# dropped or renamed, so an older build reading this file still works.
_JOB_COLUMNS = {
    "client_id": "TEXT NOT NULL DEFAULT ''",
    "status": "TEXT NOT NULL DEFAULT 'quoted'",
    "source": "TEXT NOT NULL DEFAULT 'calculator'",
    "scheduled_at": "TEXT NOT NULL DEFAULT ''",
    "completed_at": "TEXT",
    "paid_at": "TEXT",
    "receipt_ref": "TEXT NOT NULL DEFAULT ''",
    "updated_at": "TEXT",
}

_CLIENTS = """
CREATE TABLE IF NOT EXISTS clients (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    phone      TEXT,
    area       TEXT NOT NULL DEFAULT '',
    estate     TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

# mpesa_ref UNIQUE where not null -- the duplicate-payment defence at the
# database level, so it holds even if a caller bypasses the domain check.
_PAYMENTS = """
CREATE TABLE IF NOT EXISTS payments (
    id          TEXT PRIMARY KEY,
    job_ref     TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    method      TEXT NOT NULL DEFAULT 'mpesa',
    mpesa_ref   TEXT,
    recorded_by TEXT NOT NULL DEFAULT 'mercy',
    recorded_at TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_mpesa_ref
    ON payments(mpesa_ref) WHERE mpesa_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_payments_job ON payments(job_ref);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteJobRepository:
    def __init__(self, db_path: str) -> None:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.executescript(_CLIENTS)
        self._conn.executescript(_PAYMENTS)
        self._migrate_leads_to_jobs()
        self._conn.commit()

    # ── migration ───────────────────────────────────────────────────────────

    def _migrate_leads_to_jobs(self) -> None:
        """Grow `leads` into the job spine. Idempotent.

        ALTER TABLE ADD COLUMN, never a rename-and-copy: the leads table holds
        real quotes Mercy has sent, and the cheapest way to lose them is a
        clever migration. Existing rows keep every value they had and simply
        gain job fields at their defaults -- which is exactly
        `status='quoted', source='calculator'`, the correct reading of a lead
        that came from the calculator and has not been acted on.
        """
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(leads)")}
        if not have:
            return  # fresh database; the leads table is created by the lead store
        for col, decl in _JOB_COLUMNS.items():
            if col not in have:
                self._conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {decl}")

        # Backfill a client per distinct (name, phone). Done here rather than in
        # a separate pass so a half-migrated database cannot exist.
        rows = self._conn.execute(
            "SELECT ref, name, phone, area, estate, timestamp FROM leads "
            "WHERE client_id = '' OR client_id IS NULL"
        ).fetchall()
        for r in rows:
            key = (r["name"] or "", r["phone"] or "")
            existing = self._conn.execute(
                "SELECT id FROM clients WHERE name = ? AND IFNULL(phone,'') = ?",
                (key[0], key[1]),
            ).fetchone()
            cid = existing["id"] if existing else f"cl-{uuid.uuid4().hex[:12]}"
            if not existing:
                self._conn.execute(
                    "INSERT INTO clients (id,name,phone,area,estate,notes,created_at) "
                    "VALUES (?,?,?,?,?,'',?)",
                    (cid, key[0], key[1] or None, r["area"] or "", r["estate"] or "",
                     r["timestamp"] or _now_iso()),
                )
            self._conn.execute(
                "UPDATE leads SET client_id = ?, updated_at = IFNULL(updated_at, timestamp) "
                "WHERE ref = ?",
                (cid, r["ref"]),
            )

    # ── reads ───────────────────────────────────────────────────────────────

    def _payments_for(self, ref: str) -> list[Payment]:
        rows = self._conn.execute(
            "SELECT * FROM payments WHERE job_ref = ? ORDER BY recorded_at ASC", (ref,)
        ).fetchall()
        return [
            Payment(
                id=r["id"],
                job_ref=r["job_ref"],
                amount_cents=r["amount"],
                kind=PaymentKind(r["kind"]),
                method=PaymentMethod(r["method"]),
                mpesa_ref=r["mpesa_ref"],
                recorded_by=r["recorded_by"],
                recorded_at=datetime.fromisoformat(r["recorded_at"]),
                note=r["note"],
            )
            for r in rows
        ]

    def _to_job(self, r: sqlite3.Row) -> Job:
        return Job(
            ref=r["ref"],
            client_id=r["client_id"] or "",
            client_name=r["name"],
            items=r["items"] or "",
            subtotal_cents=r["subtotal"],
            discount_cents=r["discount"],
            total_cents=r["total"],
            visit_first=bool(r["visit_first"]),
            status=JobStatus(r["status"]),
            source=JobSource(r["source"]),
            area=r["area"] or "",
            estate=r["estate"] or "",
            preferred=r["preferred"] or "",
            scheduled_at=r["scheduled_at"] or "",
            completed_at=datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None,
            paid_at=datetime.fromisoformat(r["paid_at"]) if r["paid_at"] else None,
            receipt_ref=r["receipt_ref"] or "",
            created_at=datetime.fromisoformat(r["timestamp"]),
            updated_at=datetime.fromisoformat(r["updated_at"] or r["timestamp"]),
            payments=self._payments_for(r["ref"]),
        )

    def get(self, ref: str) -> Job | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM leads WHERE ref = ?", (ref,)).fetchone()
        return self._to_job(r) if r else None

    def list(self, status: str | None = None) -> list[Job]:
        q = "SELECT * FROM leads"
        args: tuple = ()
        if status:
            q += " WHERE status = ?"
            args = (status,)
        q += " ORDER BY timestamp DESC"
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [self._to_job(r) for r in rows]

    def get_client(self, cid: str) -> Client | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
        if not r:
            return None
        return Client(
            id=r["id"], name=r["name"], phone=r["phone"], area=r["area"],
            estate=r["estate"], notes=r["notes"],
            created_at=datetime.fromisoformat(r["created_at"]),
        )

    # ── writes ──────────────────────────────────────────────────────────────

    def save(self, job: Job) -> None:
        """Persist the job's own fields. Payments are NOT written here -- they
        are append-only and go through add_payment, so a save can never rewrite
        payment history."""
        with self._lock:
            self._conn.execute(
                "UPDATE leads SET status=?, source=?, scheduled_at=?, completed_at=?, "
                "paid_at=?, receipt_ref=?, client_id=?, updated_at=? WHERE ref=?",
                (
                    job.status.value, job.source.value, job.scheduled_at,
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.paid_at.isoformat() if job.paid_at else None,
                    job.receipt_ref, job.client_id, _now_iso(), job.ref,
                ),
            )
            self._conn.commit()

    def add_payment(self, p: Payment) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO payments (id,job_ref,amount,kind,method,mpesa_ref,"
                "recorded_by,recorded_at,note) VALUES (?,?,?,?,?,?,?,?,?)",
                (p.id, p.job_ref, p.amount_cents, p.kind.value, p.method.value,
                 p.mpesa_ref, p.recorded_by, p.recorded_at.isoformat(), p.note),
            )
            self._conn.commit()
