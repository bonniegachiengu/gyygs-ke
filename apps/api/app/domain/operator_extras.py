"""Operator-only deviations from the engine's price — MYRAH_OPERATIONS_DESIGN §3b/§3c.

The engine stays authoritative for everything it knows about. This module is
the narrow, explicit, auditable exception: after a site visit or on the morning
of a clean, Mercy sometimes needs a number the catalogue cannot produce.

  - a CUSTOM LINE for work the catalogue has no entry for ("chandelier crystals")
  - a PRICE OVERRIDE on one engine line ("that sofa was far worse than described")

Two rules make this safe rather than a hole in server-authoritative pricing:

1. **It is operator-only.** Nothing on the customer lane can reach this. A
   customer still cannot influence their own price by a shilling.
2. **Every deviation names itself.** Each one produces a sentence for the change
   log, so "why is it more than you said?" always has an answer — the same
   append-only discipline §8 applies to money.

An override is keyed by line INDEX *and* the label captured when it was set. If
the basket has moved underneath it the labels no longer match and the whole
re-price is refused, rather than silently repricing a different line. Getting
that wrong would change a number nobody chose to change.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.core.errors import DomainError
from app.domain.models import QuoteLine


class CustomLine(BaseModel):
    """Work the catalogue has no entry for. Priced entirely by the operator,
    because by definition the engine has nothing to say about it."""

    label: str = Field(min_length=1, max_length=80)
    amount: int = Field(ge=0, le=10_000_000)   # whole shillings, like the engine
    note: str = Field("", max_length=500)


class LineOverride(BaseModel):
    """A replacement amount for one engine-priced line."""

    index: int = Field(ge=0)
    # Captured when the override was set. The staleness guard — see module docs.
    label: str = Field(min_length=1, max_length=200)
    amount: int = Field(ge=0, le=10_000_000)
    reason: str = Field("", max_length=200)


class OperatorExtras(BaseModel):
    custom_lines: list[CustomLine] = Field(default_factory=list)
    overrides: list[LineOverride] = Field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.custom_lines and not self.overrides


@dataclass(frozen=True)
class Adjusted:
    lines: list[QuoteLine]
    subtotal: int
    total: int
    #: One human sentence per deviation, for the change log.
    notes: list[str]


def ksh(n: int) -> str:
    return f"KSh {n:,}"


def apply_operator_extras(
    *,
    lines: list[QuoteLine],
    subtotal: int,
    total: int,
    extras: OperatorExtras,
) -> Adjusted:
    """Apply overrides and custom lines to an engine result.

    The new total moves by exactly the DELTA to the subtotal, rather than being
    recomputed from scratch. Recomputing would silently re-derive the discount,
    VAT and call-out floor from the operator's own figure — quietly changing
    things Mercy did not touch. A delta changes only what she changed.
    """
    if extras.empty:
        return Adjusted(list(lines), subtotal, total, [])

    out = [QuoteLine(label=l.label, amount=l.amount) for l in lines]
    notes: list[str] = []

    for ov in extras.overrides:
        if ov.index >= len(out):
            raise DomainError(
                f"the basket changed — line {ov.index + 1} no longer exists. "
                "Re-check the prices before saving.",
                field="operator.overrides",
            )
        current = out[ov.index]
        if current.label != ov.label:
            raise DomainError(
                f"the basket changed — line {ov.index + 1} is now "
                f"'{current.label}', not '{ov.label}'. Re-check the prices "
                "before saving.",
                field="operator.overrides",
            )
        if ov.amount == current.amount:
            continue                     # not actually an override
        notes.append(
            f"{current.label}: {ksh(current.amount)} → {ksh(ov.amount)}"
            + (f" ({ov.reason})" if ov.reason else "")
        )
        out[ov.index] = QuoteLine(label=current.label, amount=ov.amount)

    for cl in extras.custom_lines:
        out.append(QuoteLine(label=cl.label, amount=cl.amount))
        notes.append(
            f"added '{cl.label}' {ksh(cl.amount)}" + (f" ({cl.note})" if cl.note else "")
        )

    new_subtotal = sum(l.amount for l in out)
    return Adjusted(out, new_subtotal, total + (new_subtotal - subtotal), notes)
