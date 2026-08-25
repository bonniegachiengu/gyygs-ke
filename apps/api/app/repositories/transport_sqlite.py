"""Transport fees by zone — MYRAH_OPERATIONS_DESIGN.md §3d.

The fees are DATA, not code. Mercy sets them from the operator board: she knows
her patch, and nobody should need a deploy to change a number she decides.

Seeded from the catalogue's own areas the first time it runs, at 0 — deliberately
zero rather than a figure invented on her behalf. A zero fee behaves exactly like
today's "no transport line", so the mechanism can ship and be tested before she
has set a single number, and nothing quietly starts charging her clients a price
nobody chose.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_TABLE = """
CREATE TABLE IF NOT EXISTS transport_zones (
  area_key   TEXT PRIMARY KEY,
  label      TEXT NOT NULL DEFAULT '',
  fee        INTEGER NOT NULL DEFAULT 0,   -- whole shillings, like the engine
  confirm    INTEGER NOT NULL DEFAULT 0,   -- 1 = quote it, but confirm coverage
  updated_at TEXT NOT NULL DEFAULT ''
)
"""


class SqliteTransportRepository:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute(_TABLE)
            self._db.commit()

    def seed(self, areas) -> None:
        """Insert any area that has no row yet, at fee 0.

        INSERT OR IGNORE, so a fee Mercy has already set is never overwritten by
        a later deploy — the seed is a floor, not a reset.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            for a in areas:
                self._db.execute(
                    "INSERT OR IGNORE INTO transport_zones"
                    " (area_key, label, fee, confirm, updated_at) VALUES (?,?,?,?,?)",
                    (a.key, a.label, 0, 1 if getattr(a, "visit", False) else 0, now),
                )
            self._db.commit()

    def list_zones(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT area_key, label, fee, confirm, updated_at"
                " FROM transport_zones ORDER BY rowid"
            ).fetchall()
        return [
            {
                "area_key": r["area_key"],
                "label": r["label"],
                "fee": int(r["fee"]),
                "confirm": bool(r["confirm"]),
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def fee_for(self, area_key: str) -> int:
        """0 for an unknown area rather than an error.

        A missing zone must never break a quote: the cleaning price is still
        correct and Mercy confirms the trip. Refusing to price the whole job
        because a zone row is absent would be a worse failure than a 0.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT fee FROM transport_zones WHERE area_key = ?", (area_key,)
            ).fetchone()
        return int(row["fee"]) if row else 0

    def set_fee(self, area_key: str, fee: int) -> None:
        if fee < 0:
            raise ValueError("a transport fee cannot be negative")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._db.execute(
                "UPDATE transport_zones SET fee = ?, updated_at = ? WHERE area_key = ?",
                (int(fee), now, area_key),
            )
            if cur.rowcount == 0:
                raise KeyError(area_key)
            self._db.commit()
