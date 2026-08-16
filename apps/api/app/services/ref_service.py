"""Quote references — `MY-YYMMDD-nnn` (ARCHITECTURE.md §5).

`nnn` is a per-day sequence. Google Sheets is not transactional and a read-then-
write per quote would cost a round trip on the Kenyan mobile path, so the counter
is local and durable, reconciled against the repository once at startup.

Restart behaviour:
  * counter file intact                -> continues                     OK
  * file lost, repository reachable    -> reseeded from the stored refs  OK
  * file intact, repository down       -> continues                      OK
  * both lost                          -> restarts at 001; `Lead.lead_id`
                                          still identifies the row uniquely

Gaps (a ref allocated for a quote that then failed to persist) are expected and
harmless — the ref is a display identity, not a primary key.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

#: EAT has never observed DST, so a fixed offset avoids depending on tzdata
#: being present on Windows.
NAIROBI = timezone(timedelta(hours=3), "EAT")


def daykey_for(now: datetime) -> str:
    """YYMMDD in Nairobi time.

    `created_at` stays UTC per §5, but the reference must carry the Kenyan date —
    otherwise a quote taken at 01:30 EAT would be filed under yesterday and
    Mercy's refs would not line up with her day.
    """
    return now.astimezone(NAIROBI).strftime("%y%m%d")


class SequenceStore(Protocol):
    def next(self, daykey: str) -> int: ...
    def peek(self, daykey: str) -> int: ...
    def seed(self, daykey: str, value: int) -> None: ...


class MemorySequenceStore:
    def __init__(self) -> None:
        self._day: str | None = None
        self._seq = 0
        self._lock = threading.Lock()

    def next(self, daykey: str) -> int:
        with self._lock:
            if self._day != daykey:
                self._day, self._seq = daykey, 0
            self._seq += 1
            return self._seq

    def peek(self, daykey: str) -> int:
        with self._lock:
            return self._seq if self._day == daykey else 0

    def seed(self, daykey: str, value: int) -> None:
        with self._lock:
            if self._day != daykey:
                self._day, self._seq = daykey, value
            else:
                self._seq = max(self._seq, value)


class FileSequenceStore:
    """JSON counter on disk. Lives on a named Docker volume in production."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> tuple[str | None, int]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data.get("day"), int(data.get("seq", 0))
        except (OSError, ValueError, TypeError):
            return None, 0

    def _write(self, day: str, seq: int) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"day": day, "seq": seq}), encoding="utf-8")
        # Atomic on both Windows and Linux — a crash mid-write cannot corrupt it.
        os.replace(tmp, self._path)

    def next(self, daykey: str) -> int:
        with self._lock:
            day, seq = self._read()
            seq = seq + 1 if day == daykey else 1
            self._write(daykey, seq)
            return seq

    def peek(self, daykey: str) -> int:
        with self._lock:
            day, seq = self._read()
            return seq if day == daykey else 0

    def seed(self, daykey: str, value: int) -> None:
        with self._lock:
            day, seq = self._read()
            current = seq if day == daykey else 0
            if value > current:
                self._write(daykey, value)


class QuoteRefAllocator:
    def __init__(self, store: SequenceStore) -> None:
        self._store = store

    def next_ref(self, now: datetime) -> str:
        daykey = daykey_for(now)
        # :03d widens past 999 rather than wrapping.
        return f"MY-{daykey}-{self._store.next(daykey):03d}"

    def seed_from(self, repo_max: int, now: datetime) -> None:
        self._store.seed(daykey_for(now), repo_max)
