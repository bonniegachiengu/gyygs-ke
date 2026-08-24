"""Durable lead store on local SQLite — the store Myrah actually runs on.

Why SQLite and not Sheets or Postgres: the host is moving off Docker to native
Windows services (no-Docker direction), so the lead log must survive a restart
without adding a second service to supervise. SQLite is a file plus the stdlib —
no daemon, no port, no credentials, and it is the only option here that makes
`LEAD_STORE` durable *by default* instead of durable-if-configured. The Sheets
path stays exactly where it was for anyone who wants it; this is an additional
mode, not a replacement.

Satisfies the same `LeadRepository` Protocol as the memory and Sheets stores, so
nothing above the repository seam changes — which is the whole point of
ARCHITECTURE.md §7.

Concurrency: one connection with `check_same_thread=False` guarded by a lock.
uvicorn runs sync endpoint bodies on a threadpool, so a bare connection would be
touched from several threads; the lock is what makes that safe, and the write
volume here (one row per quote) is nowhere near needing a pool.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from app.repositories.base import Lead

# Column order mirrors Lead / ARCHITECTURE §7 so the table reads like the sheet
# it replaces. `ref` is the primary key: one row per quote reference.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    ref         TEXT PRIMARY KEY,
    timestamp   TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    phone       TEXT,
    items       TEXT    NOT NULL,
    subtotal    INTEGER NOT NULL,
    discount    INTEGER NOT NULL,
    total       INTEGER NOT NULL,
    area        TEXT    NOT NULL,
    estate      TEXT    NOT NULL DEFAULT '',
    preferred   TEXT    NOT NULL DEFAULT '',
    visit_first INTEGER NOT NULL DEFAULT 0,
    sent_to_wa  INTEGER NOT NULL DEFAULT 0,
    lead_id     TEXT    NOT NULL DEFAULT ''
);
"""


class SqliteLeadRepository:
    def __init__(self, db_path: str) -> None:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL: a reader (the ops list) never blocks the writer (a live quote).
        # Durability is unaffected — WAL is still crash-safe.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @staticmethod
    def _to_lead(row: sqlite3.Row) -> Lead:
        return Lead(
            ref=row["ref"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            name=row["name"],
            phone=row["phone"],
            items=row["items"],
            subtotal=row["subtotal"],
            discount=row["discount"],
            total=row["total"],
            area=row["area"],
            estate=row["estate"],
            preferred=row["preferred"],
            visit_first=bool(row["visit_first"]),
            sent_to_wa=bool(row["sent_to_wa"]),
            lead_id=row["lead_id"],
        )

    def append(self, lead: Lead) -> None:
        # INSERT OR REPLACE, not plain INSERT: a retried submit of the same ref
        # must not raise. The ref is allocated once per quote, so a repeat is a
        # replay of the same lead, never a different one.
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO leads (
                    ref, timestamp, name, phone, items, subtotal, discount, total,
                    area, estate, preferred, visit_first, sent_to_wa, lead_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    lead.ref,
                    lead.timestamp.isoformat(),
                    lead.name,
                    lead.phone,
                    lead.items,
                    lead.subtotal,
                    lead.discount,
                    lead.total,
                    lead.area,
                    lead.estate,
                    lead.preferred,
                    int(lead.visit_first),
                    int(lead.sent_to_wa),
                    lead.lead_id,
                ),
            )
            self._conn.commit()

    def list(self) -> list[Lead]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM leads ORDER BY timestamp ASC, ref ASC"
            ).fetchall()
        return [self._to_lead(r) for r in rows]

    def mark_sent(self, ref: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE leads SET sent_to_wa = 1 WHERE ref = ?", (ref,)
            )
            self._conn.commit()
            # rowcount is 1 even when the row was already sent, which is exactly
            # the idempotent "yes, that ref exists and is now sent" the Protocol
            # asks for. 0 means the ref is genuinely unknown.
            return cur.rowcount > 0

    def max_sequence_for(self, daykey: str) -> int:
        # Same MY-{daykey}-nnn shape the memory store parses, done in SQL. The
        # tail is compared as an integer, not lexically, so 010 < 9 can't happen.
        prefix = f"MY-{daykey}-"
        with self._lock:
            rows = self._conn.execute(
                "SELECT ref FROM leads WHERE ref LIKE ? || '%'", (prefix,)
            ).fetchall()
        best = 0
        for r in rows:
            tail = r["ref"][len(prefix) :]
            if tail.isdigit():
                best = max(best, int(tail))
        return best
