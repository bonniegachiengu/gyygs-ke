"""Lead storage behind an interface — ARCHITECTURE.md §7.

Google Sheets today, Postgres later, with no change to callers. That swap is the
whole reason this seam exists, so nothing above it may import a concrete store.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """One row per quote. Column order is ARCHITECTURE §7, verbatim."""

    ref: str
    timestamp: datetime
    name: str
    phone: str | None
    items: str  # json.dumps of the request's items + addons
    subtotal: int
    discount: int
    total: int
    area: str
    preferred: str  # "2026-08-16 morning", or "" when unspecified
    visit_first: bool
    sent_to_wa: bool
    # Additive trailing column: the quote_ref is a display identity and could in
    # principle repeat if the counter and the sheet were both lost. This never does.
    lead_id: str = Field(default="")


class LeadRepository(Protocol):
    def append(self, lead: Lead) -> None: ...

    def list(self) -> list[Lead]: ...

    def mark_sent(self, ref: str) -> bool:
        """Flip sent_to_wa. Idempotent. False if the ref is unknown."""
        ...

    def max_sequence_for(self, daykey: str) -> int:
        """Highest nnn already used on `daykey` (YYMMDD), or 0. Seeds the counter."""
        ...
