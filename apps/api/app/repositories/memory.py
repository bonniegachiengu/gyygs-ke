"""In-memory lead store — the default until Google credentials land (M2).

Satisfies the same Protocol as the Sheets store, so quotes compute and hand off
correctly today; only the durable log is missing.
"""

from __future__ import annotations

import threading

from app.repositories.base import Lead


class MemoryLeadRepository:
    def __init__(self) -> None:
        self._leads: list[Lead] = []
        self._lock = threading.Lock()

    def append(self, lead: Lead) -> None:
        with self._lock:
            self._leads.append(lead)

    def list(self) -> list[Lead]:
        with self._lock:
            return list(self._leads)

    def mark_sent(self, ref: str) -> bool:
        with self._lock:
            for i, lead in enumerate(self._leads):
                if lead.ref == ref:
                    self._leads[i] = lead.model_copy(update={"sent_to_wa": True})
                    return True
        return False

    def max_sequence_for(self, daykey: str) -> int:
        prefix = f"MY-{daykey}-"
        best = 0
        with self._lock:
            for lead in self._leads:
                if lead.ref.startswith(prefix):
                    tail = lead.ref[len(prefix) :]
                    if tail.isdigit():
                        best = max(best, int(tail))
        return best
