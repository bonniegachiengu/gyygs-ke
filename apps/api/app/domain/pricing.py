"""The pricing engine — pure functions, no I/O, no clock, no config object.

ARCHITECTURE.md §6 defines the algorithm; PRICES.md defines the numbers. Anything
that needs the outside world (the quote reference, the lead row, the WhatsApp URL)
lives in `services/`, not here, so this module is trivially unit-testable and the
tests are the gate on revenue correctness.

Order of operations, exactly:

    1. line   = (base + additive modifiers) x qty          per item, then per add-on
    2. subtotal = sum(lines)
    3. discount = subtotal * pct // 100     if recurring   (integer floor)
    4. floored  = max(subtotal - discount, minimum_callout)
    5. vat      = floored * rate / 100      if VAT-registered   (exclusive)
    6. total    = floored + vat
    7. visit_first = any visit/from/range item  (or a recurring basket, if the
       recurring_requires_visit rule is on)

Transport is NEVER a line and never enters the subtotal — PRICES.md §I. It is
returned as a note, and `test_transport_never_added` pins that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.core.errors import DomainError
from app.domain.models import (
    Addon,
    PricingCatalogue,
    QuoteAddon,
    QuoteItem,
    QuoteLine,
    QuoteRequest,
    Service,
)
from app.domain.pricing_data import CATALOGUE

#: Was ARCHITECTURE §5's "charged separately ... confirmed on WhatsApp".
#: MYRAH_OPERATIONS_DESIGN.md §3d moved transport INTO the quote, priced by
#: area, so that sentence became untrue and stopped being said.
TRANSPORT_NOTE: Final[str] = "Transport for your area is included above."

#: Shown when the zone has no fee set yet, or the area needs a coverage check.
#: Honest about the gap rather than implying a KSh 0 trip.
TRANSPORT_NOTE_UNSET: Final[str] = "Transport for your area is confirmed on WhatsApp."

#: QUOTE_CALCULATOR_SPEC §6a — shown only on quotes that named a business.
ETIMS_NOTE: Final[str] = "A KRA-compliant eTIMS tax invoice will be issued on payment."

_SEP: Final[str] = " — "  # em dash, matches SPEC §3 / §7 line format


@dataclass(frozen=True)
class LineResult:
    label: str
    amount: int
    visit: bool = False


@dataclass(frozen=True)
class Computation:
    lines: list[QuoteLine]
    subtotal: int
    discount: int
    total: int
    vat: int
    visit_first: bool
    minimum_applied: bool
    #: Travel to the job, by area (MYRAH_OPERATIONS_DESIGN.md §3d). Its own row
    #: under the subtotal, NOT an item line, so `sum(lines) == subtotal` holds.
    transport: int = 0

    @property
    def minimum_adjustment(self) -> int:
        """What the call-out floor added. 0 when the floor did not bite.

        Rendered as its own row under the subtotal (Bonnie's call), rather than
        as an item line — so `sum(lines) == subtotal` stays true and the §5
        response shape is untouched.
        """
        return self.total - self.vat - self.transport - (self.subtotal - self.discount)


# ─────────────────────────────── helpers ────────────────────────────────


def _qty_suffix(qty: int) -> str:
    return f" ×{qty}" if qty > 1 else ""


def _money(n: int) -> str:
    return f"{n:,}"


def _lookup_service(key: str, cat: PricingCatalogue) -> Service:
    for s in cat.services:
        if s.key == key:
            return s
    raise DomainError(f"unknown service '{key}'", field="items.service")


def _lookup_addon(key: str, cat: PricingCatalogue) -> Addon:
    for a in cat.addons:
        if a.key == key:
            return a
    raise DomainError(f"unknown add-on '{key}'", field="addons.key")


# ──────────────────────────── item strategies ───────────────────────────


def _price_per_unit(item: QuoteItem, svc: Service) -> list[LineResult]:
    """Sofa: seats x rate, floored at min_units (a 2-seater is the 1,000 floor)."""
    rate = svc.rate or 0
    floor = svc.min_units or 1
    units = max(item.seats or floor, floor)
    if svc.max_units and units > svc.max_units:
        raise DomainError(
            f"{svc.label.lower()} tops out at {svc.max_units} {svc.unit}s", field="items.seats"
        )

    # Singular matters now that a single seat is quotable (no 2-seat floor).
    unit_word = svc.unit if units == 1 else f"{svc.unit}s"
    lines = [
        LineResult(
            label=f"{svc.label}{_SEP}{units} {unit_word}{_qty_suffix(item.qty)}",
            amount=rate * units * item.qty,
        )
    ]

    # Dining / office chairs are separate priced items, not part of the seat count.
    by_key = {e.key: e for e in (svc.extras or [])}
    for extra in item.extras:
        defn = by_key.get(extra.key)
        if defn is None:
            raise DomainError(f"unknown extra '{extra.key}'", field="items.extras")
        lines.append(
            LineResult(
                label=f"Add-on{_SEP}{defn.label}{_qty_suffix(extra.qty)}",
                amount=defn.price * extra.qty,
            )
        )
    return lines


def _price_tier(item: QuoteItem, svc: Service) -> list[LineResult]:
    """Whole-house: a bedroom tier, plus +1,500 per bedroom beyond 4."""
    if not item.tier:
        raise DomainError(f"choose a size for {svc.label.lower()}", field="items.tier")
    tiers = {t.key: t for t in (svc.tiers or [])}
    tier = tiers.get(item.tier)
    if tier is None:
        raise DomainError(f"unknown {svc.key} size '{item.tier}'", field="items.tier")

    lines = [
        LineResult(
            label=f"{svc.label}{_SEP}{tier.label}{_qty_suffix(item.qty)}",
            amount=tier.price * item.qty,
        )
    ]

    if item.extra_bedrooms:
        if svc.extra is None:
            raise DomainError(f"{svc.label.lower()} has no extra-bedroom option")
        # "each beyond 4" — only meaningful on the largest tier.
        top = (svc.tiers or [])[-1]
        if tier.key != top.key:
            raise DomainError(
                f"extra bedrooms only apply beyond {top.label}", field="items.extra_bedrooms"
            )
        lines.append(
            LineResult(
                label=f"{svc.extra.label}{_qty_suffix(item.extra_bedrooms)}",
                amount=svc.extra.price * item.extra_bedrooms,
            )
        )
    return lines


def _price_size_tier(item: QuoteItem, svc: Service) -> list[LineResult]:
    """Carpet and mattress: a fixed ft size, an open-ended top, or 'larger'."""
    if not item.size:
        raise DomainError(f"choose a size for {svc.label.lower()}", field="items.size")

    visit = False
    base = 0
    suffix = ""

    if svc.larger == "visit" and item.size == "larger":
        # PRICES.md §F "Larger sizes -> Quote". No number exists, so it contributes
        # nothing; the zero-amount line keeps the request visible to Mercy.
        biggest = (svc.tiers or [])[-1].label
        label_core = f"{svc.label}{_SEP}larger than {biggest}"
        suffix = " (on site visit)"
        visit = True
    elif svc.above is not None and item.size == svc.above.key:
        base = svc.above.price
        label_core = f"{svc.label}{_SEP}{svc.above.label}"
        suffix = " (from)"
        visit = svc.above.from_
    else:
        tiers = {t.key: t for t in (svc.tiers or [])}
        tier = tiers.get(item.size)
        if tier is None:
            raise DomainError(f"unknown {svc.key} size '{item.size}'", field="items.size")
        base = tier.price
        label_core = f"{svc.label}{_SEP}{tier.label}"

    # Modifiers are ADDITIVE — see Modifier's docstring for why, and why the test
    # asserts on a 6x9 carpet rather than a 5x7.
    by_key = {m.key: m for m in (svc.modifiers or [])}
    for key in item.modifiers:
        mod = by_key.get(key)
        if mod is None:
            raise DomainError(f"unknown modifier '{key}'", field="items.modifiers")
        if mod.add_range is not None:
            lo, hi = mod.add_range
            base += lo  # lower bound only; never quote above what they will pay
            suffix += f" ({mod.label} +{_money(lo)}–{_money(hi)})"
            visit = True
        elif mod.add is not None:
            base += mod.add
            suffix += f" ({mod.label} +{_money(mod.add)})"

    return [
        LineResult(
            label=f"{label_core}{_qty_suffix(item.qty)}{suffix}",
            amount=base * item.qty,
            visit=visit,
        )
    ]


def _price_visit(item: QuoteItem, svc: Service) -> list[LineResult]:
    """Post-construction, commercial, 'something else' — priced on a visit."""
    base = svc.from_ or 0
    suffix = " (from)" if svc.from_ else " (on site visit)"
    label = f"{svc.label}{suffix}"
    if item.note:
        label = f"{svc.label}{_SEP}{item.note.strip()}{suffix}"
    return [LineResult(label=label, amount=base * item.qty, visit=True)]


def price_item(item: QuoteItem, cat: PricingCatalogue = CATALOGUE) -> list[LineResult]:
    svc = _lookup_service(item.service, cat)
    match svc.strategy:
        case "per_unit":
            return _price_per_unit(item, svc)
        case "tier":
            return _price_tier(item, svc)
        case "size_tier":
            return _price_size_tier(item, svc)
        case "visit":
            return _price_visit(item, svc)
        case _:  # pragma: no cover — Strategy is a closed Literal
            raise DomainError(f"unsupported strategy '{svc.strategy}'")


def price_addon(addon: QuoteAddon, cat: PricingCatalogue = CATALOGUE) -> LineResult:
    defn = _lookup_addon(addon.key, cat)
    label = f"Add-on{_SEP}{defn.label}{_qty_suffix(addon.qty)}"

    if defn.price_range is not None:
        lo, hi = defn.price_range
        return LineResult(
            label=f"{label} ({_money(lo)}–{_money(hi)})", amount=lo * addon.qty, visit=True
        )

    price = defn.price or 0
    if defn.from_:
        return LineResult(label=f"{label} (from)", amount=price * addon.qty, visit=True)
    return LineResult(label=label, amount=price * addon.qty)


# ──────────────────────────────── assembly ──────────────────────────────


def compute_quote(
    req: QuoteRequest,
    cat: PricingCatalogue = CATALOGUE,
    *,
    vat_registered: bool = False,
    vat_rate: int = 16,
    repeat_customer: bool = False,
    transport: int = 0,
) -> Computation:
    """`repeat_customer` — NOT `req.recurring` — is what earns the discount.

    `req.recurring` is the customer ticking "I'll want this regularly": intent,
    logged for Mercy, worth nothing on its own. Anyone could tick it on a first
    job and take 10% off having promised nothing, and at a 50-55% gross margin
    that is ~20% of the margin given to someone who may never return.

    Nothing in v1 sets `repeat_customer` true — there is no customer record yet,
    so every quote is priced as a first job. Booking (Phase 3) is what will set
    it, at which point the discount lands where it was earned. The parameter
    exists now so the engine and its tests already describe the real rule.
    """
    if not any(a.key == req.area for a in cat.areas):
        raise DomainError(f"unknown area '{req.area}'", field="area")
    if not req.items and not req.addons:
        raise DomainError("pick at least one service to see your price", field="items")

    results: list[LineResult] = []
    for item in req.items:
        results.extend(price_item(item, cat))
    for addon in req.addons:
        results.append(price_addon(addon, cat))

    lines = [QuoteLine(label=r.label, amount=r.amount) for r in results]
    subtotal = sum(r.amount for r in results)

    discount = (
        (subtotal * cat.rules.recurring_discount_pct) // 100  # integer floor, no cents
        if repeat_customer
        else 0
    )

    # ARCHITECTURE §6, not QUOTE_CALCULATOR_SPEC §6: the floor is compared against
    # the DISCOUNTED value. The two only differ when a discount pushes a basket
    # under the floor, and §6 of the tech contract is the precise statement.
    net = subtotal - discount
    floored = max(net, cat.minimum_callout)
    minimum_applied = floored > net

    # PRICES.md §J: flyer prices are final for a non-VAT business; if Myrah ever
    # registers, 16% applies ON TOP.
    # Transport lands AFTER the discount and AFTER the floor, deliberately.
    #
    # The repeat discount is a thank-you on Myrah's LABOUR; letting it erode the
    # travel fee would quietly discount her fuel, which she pays either way. The
    # call-out floor likewise measures the size of the CLEANING job, not how far
    # she drove to reach it. VAT, if she ever registers, applies to the whole
    # charge including travel, so transport goes in before VAT is taken.
    transport = max(0, int(transport))
    charged = floored + transport

    vat = (charged * vat_rate + 50) // 100 if vat_registered else 0
    total = charged + vat

    visit_first = any(r.visit for r in results) or (
        req.recurring and cat.rules.recurring_requires_visit
    )

    return Computation(
        lines=lines,
        subtotal=subtotal,
        discount=discount,
        total=total,
        vat=vat,
        visit_first=visit_first,
        minimum_applied=minimum_applied,
        transport=transport,
    )
