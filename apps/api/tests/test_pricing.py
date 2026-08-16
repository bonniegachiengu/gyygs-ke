"""Pricing engine tests — ARCHITECTURE.md §6 makes these mandatory.

"Pricing tests are the gate that protects revenue correctness." (§12)
"""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.domain.models import Contact, QuoteAddon, QuoteItem, QuoteItemExtra, QuoteRequest
from app.domain.pricing import TRANSPORT_NOTE, compute_quote
from app.domain.pricing_data import build_catalogue

CAT = build_catalogue()


def quote(**kw) -> QuoteRequest:
    kw.setdefault("area", "ruiru")
    kw.setdefault("contact", Contact(name="Faith"))
    return QuoteRequest(**kw)


def totals(req: QuoteRequest, **kw):
    return compute_quote(req, CAT, **kw)


# ─────────────────────── the worked example (the headline) ───────────────────────


def test_worked_example_3800_ruiru() -> None:
    """DISPATCH_BRIEF DoD: 3-seat sofa 1,500 + mattress 5x6 1,500 + fridge 800."""
    c = totals(
        quote(
            items=[
                QuoteItem(service="sofa", seats=3),
                QuoteItem(service="mattress", size="5x6"),
            ],
            addons=[QuoteAddon(key="fridge")],
        )
    )

    assert [(line.label, line.amount) for line in c.lines] == [
        ("Sofa — 3 seats", 1500),
        ("Mattress — 5×6", 1500),
        ("Add-on — Fridge", 800),
    ]
    assert c.subtotal == 3800
    assert c.discount == 0
    assert c.total == 3800
    assert c.visit_first is False
    assert c.vat == 0


# ──────────────────────────── one per service (§6) ────────────────────────────


@pytest.mark.parametrize(
    ("tier", "price"),
    [("studio", 2500), ("1br", 3500), ("2br", 5000), ("3br", 6500), ("4br", 8000)],
)
def test_house_tiers(tier: str, price: int) -> None:
    c = totals(quote(items=[QuoteItem(service="house", tier=tier)]))
    assert c.subtotal == price
    assert c.visit_first is False


@pytest.mark.parametrize(
    ("seats", "price"),
    [(2, 1000), (3, 1500), (4, 2000), (5, 2500), (6, 3000), (7, 3500), (8, 4000), (9, 4500)],
)
def test_sofa_seaters(seats: int, price: int) -> None:
    assert totals(quote(items=[QuoteItem(service="sofa", seats=seats)])).subtotal == price


@pytest.mark.parametrize(
    ("size", "price"),
    [
        ("3x5", 500),
        ("4x6", 700),
        ("5x7", 1000),
        ("6x9", 1300),
        ("8x10", 1800),
        ("9x12", 2200),
        ("10x14", 2800),
    ],
)
def test_carpet_sizes(size: str, price: int) -> None:
    c = totals(quote(items=[QuoteItem(service="carpet", size=size)]))
    assert c.subtotal == price
    assert c.visit_first is False


@pytest.mark.parametrize(
    ("size", "price"), [("3x6", 1000), ("4x6", 1200), ("5x6", 1500), ("6x6", 1800)]
)
def test_mattress_sizes(size: str, price: int) -> None:
    assert totals(quote(items=[QuoteItem(service="mattress", size=size)])).subtotal == price


def test_post_construction_is_from_10000_and_visit_first() -> None:
    c = totals(quote(items=[QuoteItem(service="post_construction")]))
    assert c.subtotal == 10000
    assert c.visit_first is True
    assert c.lines[0].label == "Post-construction (from)"


@pytest.mark.parametrize(
    ("key", "price"),
    [
        ("kitchen_deep", 1500),
        ("fridge", 800),
        ("oven", 800),
        ("microwave", 400),
        ("balcony", 500),
        ("declutter_light", 500),
    ],
)
def test_flat_addons(key: str, price: int) -> None:
    c = totals(quote(addons=[QuoteAddon(key=key)]))
    # These are hard prices, so the quote stays instant.
    assert c.visit_first is False
    assert c.subtotal == price


def test_per_unit_addons_multiply_and_label_quantity() -> None:
    c = totals(quote(addons=[QuoteAddon(key="bathroom", qty=3)]))
    assert c.subtotal == 2400
    assert c.lines[0].label == "Add-on — Bathroom / Toilet ×3"

    c2 = totals(quote(addons=[QuoteAddon(key="windows_inside", qty=6)]))
    assert c2.subtotal == 900


# ─────────────────────────── the §6 edge cases, by name ───────────────────────────


def test_minimum_callout_floor() -> None:
    """A single microwave is 400; the call-out floor lifts it to 1,500."""
    c = totals(quote(addons=[QuoteAddon(key="microwave")]))
    assert c.subtotal == 400
    assert c.total == 1500
    assert c.minimum_applied is True
    assert c.minimum_adjustment == 1100
    # The floor is shown as its own row under the subtotal, never folded into an
    # item line — so the itemised card still adds up to the subtotal.
    assert sum(line.amount for line in c.lines) == c.subtotal


def test_minimum_not_applied_above_the_floor() -> None:
    c = totals(quote(items=[QuoteItem(service="mattress", size="6x6")]))
    assert c.total == 1800
    assert c.minimum_applied is False
    assert c.minimum_adjustment == 0


def test_minimum_callout_is_configurable_off() -> None:
    """PRICES.md never states a floor — MINIMUM_CALLOUT=0 must honour the flyer."""
    cat = build_catalogue(minimum_callout=0)
    c = compute_quote(quote(items=[QuoteItem(service="sofa", seats=2)]), cat)
    assert c.total == 1000  # the flyer's 2-seater price, not 1,500


def test_extra_bedroom_beyond_4br() -> None:
    c = totals(quote(items=[QuoteItem(service="house", tier="4br", extra_bedrooms=2)]))
    assert [(line.label, line.amount) for line in c.lines] == [
        ("Whole-house deep clean — 4 Bedroom", 8000),
        ("Extra bedroom ×2", 3000),
    ]
    assert c.subtotal == 11000


def test_extra_bedroom_rejected_below_top_tier() -> None:
    with pytest.raises(DomainError, match="beyond"):
        totals(quote(items=[QuoteItem(service="house", tier="2br", extra_bedrooms=1)]))


def test_thick_shaggy_is_additive_not_multiplicative() -> None:
    """The trap: on a 5x7 carpet 1000+300 and 1000*1.3 are both 1300.

    ARCHITECTURE §6 says "x (1 + modifiers)" while its own §5 data and PRICES.md
    §F say "+300-500". Asserting on a 6x9 is what tells them apart.
    """
    c = totals(quote(items=[QuoteItem(service="carpet", size="6x9", modifiers=["thick_shaggy"])]))
    assert c.subtotal == 1600  # 1300 + 300, NOT 1300 * 1.3 == 1690
    assert c.visit_first is True
    assert "+300–500" in c.lines[0].label


def test_thick_shaggy_with_quantity() -> None:
    c = totals(
        quote(items=[QuoteItem(service="carpet", size="5x7", qty=2, modifiers=["thick_shaggy"])])
    )
    assert c.subtotal == 2600  # (1000 + 300) x 2


def test_mattress_6x7_and_above_is_from_2000_and_visit_first() -> None:
    c = totals(quote(items=[QuoteItem(service="mattress", size="6x7_plus")]))
    assert c.subtotal == 2000
    assert c.visit_first is True
    assert c.lines[0].label == "Mattress — 6×7 & above (from)"


def test_carpet_larger_contributes_nothing_and_is_visit_first() -> None:
    c = totals(quote(items=[QuoteItem(service="carpet", size="larger")]))
    assert c.subtotal == 0
    assert c.visit_first is True
    assert c.lines[0].label == "Carpet / Rug — larger than 10×14 (on site visit)"


def test_visit_first_propagates_from_a_single_item() -> None:
    c = totals(quote(items=[QuoteItem(service="sofa", seats=3)], addons=[QuoteAddon(key="rust")]))
    assert c.subtotal == 2000  # 1500 + 500 (the "from" lower bound)
    assert c.visit_first is True


def test_visit_first_false_when_every_item_is_a_hard_price() -> None:
    c = totals(
        quote(items=[QuoteItem(service="house", tier="2br")], addons=[QuoteAddon(key="fridge")])
    )
    assert c.visit_first is False


# ────────────────────────────── rules and ranges ──────────────────────────────


def test_sofa_floors_at_the_two_seater_minimum() -> None:
    assert totals(quote(items=[QuoteItem(service="sofa", seats=1)])).subtotal == 1000


def test_sofa_rejects_more_than_nine_seats() -> None:
    # PRICES.md §E stops at a 9-seater; caught by the schema, not the engine.
    with pytest.raises(ValueError):
        QuoteItem(service="sofa", seats=10)


def test_sofa_chairs_are_separate_lines() -> None:
    c = totals(
        quote(
            items=[
                QuoteItem(
                    service="sofa",
                    seats=3,
                    extras=[QuoteItemExtra(key="dining_chair", qty=4)],
                )
            ]
        )
    )
    assert [(line.label, line.amount) for line in c.lines] == [
        ("Sofa — 3 seats", 1500),
        ("Add-on — Dining chair ×4", 1000),
    ]


def test_office_chair_is_350() -> None:
    c = totals(
        quote(
            items=[QuoteItem(service="sofa", seats=2, extras=[QuoteItemExtra(key="office_chair")])]
        )
    )
    assert c.subtotal == 1350


def test_recurring_discount_is_ten_percent() -> None:
    c = totals(quote(items=[QuoteItem(service="house", tier="2br")], recurring=True))
    assert c.subtotal == 5000
    assert c.discount == 500
    assert c.total == 4500


def test_recurring_discount_floors_to_whole_shillings() -> None:
    # 3,805 x 10% = 380.5 -> 380, never a fractional shilling.
    c = totals(
        quote(
            items=[QuoteItem(service="mattress", size="5x6")],
            addons=[QuoteAddon(key="windows_inside", qty=15), QuoteAddon(key="microwave")],
            recurring=True,
        )
    )
    assert c.subtotal == 1500 + 2250 + 400
    assert c.discount == c.subtotal * 10 // 100


def test_recurring_discount_then_the_minimum_floor() -> None:
    """Pins ARCHITECTURE §6 over QUOTE_CALCULATOR_SPEC §6.

    §6 of the tech contract compares the floor against the DISCOUNTED value;
    the UX spec's summary compares it against the raw subtotal. They only differ
    here: 1,600 - 10% = 1,440, which is under the 1,500 floor.
    """
    c = totals(quote(addons=[QuoteAddon(key="bathroom", qty=2)], recurring=True))
    assert c.subtotal == 1600
    assert c.discount == 160
    assert c.total == 1500  # not 1,440, and not 1,600


def test_residential_recurring_still_gets_a_real_total() -> None:
    """Bonnie's call: premises decides the visit branch, not the recurring flag."""
    c = totals(quote(items=[QuoteItem(service="house", tier="2br")], recurring=True))
    assert c.visit_first is False
    assert c.total == 4500


def test_minimum_floor_swallows_the_recurring_discount_on_small_baskets() -> None:
    """⚠ Business consequence, not a bug — flagged for Mercy.

    A 3-seat sofa is 1,500. Recurring -10% takes it to 1,350, which is under the
    1,500 call-out floor, so the customer is charged 1,500 and sees no discount
    at all. With both values at their current defaults the loyalty discount is
    invisible on every job under ~1,667 KSh — which includes the 3-seater, the
    single most common basket in the specs.

    Two dials fix it, both config: lower MINIMUM_CALLOUT, or accept that the
    discount only applies above the floor. This test pins the behaviour so the
    trade-off stays visible rather than silently surprising a repeat customer.
    """
    c = totals(quote(items=[QuoteItem(service="sofa", seats=3)], recurring=True))
    assert c.subtotal == 1500
    assert c.discount == 150
    assert c.total == 1500  # not 1,350 — the floor took the discount back
    assert c.minimum_applied is True

    # With the floor off, the discount lands as the customer expects.
    off = compute_quote(
        quote(items=[QuoteItem(service="sofa", seats=3)], recurring=True),
        build_catalogue(minimum_callout=0),
    )
    assert off.total == 1350


def test_recurring_can_be_forced_to_visit_first_by_config() -> None:
    cat = build_catalogue(recurring_requires_visit=True)
    c = compute_quote(quote(items=[QuoteItem(service="sofa", seats=3)], recurring=True), cat)
    assert c.visit_first is True


def test_inside_cabinets_range_uses_the_lower_bound_and_is_visit_first() -> None:
    c = totals(quote(addons=[QuoteAddon(key="inside_cabinets")]))
    assert c.subtotal == 500
    assert c.visit_first is True
    assert c.lines[0].label == "Add-on — Inside cabinets (500–1,000)"


@pytest.mark.parametrize("key", ["wall_spot", "rust", "grease"])
def test_from_addons_contribute_their_floor_and_are_visit_first(key: str) -> None:
    c = totals(quote(addons=[QuoteAddon(key=key)]))
    assert c.subtotal == 500
    assert c.visit_first is True
    assert c.lines[0].label.endswith("(from)")


@pytest.mark.parametrize(("key", "price"), [("declutter_room", 1000), ("declutter_house", 2500)])
def test_declutter_from_prices_are_visit_first(key: str, price: int) -> None:
    c = totals(quote(addons=[QuoteAddon(key=key)]))
    assert c.subtotal == price
    assert c.visit_first is True


def test_light_decluttering_is_a_hard_price() -> None:
    """PRICES.md §C says 500 flat; §H's page-2 restatement says "from 500".
    ARCHITECTURE §5 sides with §C, so this stays instant."""
    assert totals(quote(addons=[QuoteAddon(key="declutter_light")])).visit_first is False


# ───────────────────────────── transport and areas ─────────────────────────────


def test_transport_is_never_added_and_never_a_line() -> None:
    c = totals(
        quote(
            items=[QuoteItem(service="sofa", seats=3)],
            addons=[QuoteAddon(key="fridge")],
        )
    )
    assert sum(line.amount for line in c.lines) == c.subtotal
    assert not any("transport" in line.label.lower() for line in c.lines)
    assert TRANSPORT_NOTE == (
        "Transport charged separately based on your area — confirmed on WhatsApp."
    )


def test_area_other_does_not_make_the_quote_visit_first() -> None:
    """ARCHITECTURE §5 tags the area visit:true, but that is a COVERAGE question.

    §5 scopes visit_first to items ("true if any item is visit/quote/from") and
    QUOTE_CALCULATOR_SPEC §9 says an Other area proceeds with a note. A plain
    3-seat sofa must not lose its price because of where the customer lives.
    """
    c = totals(quote(items=[QuoteItem(service="sofa", seats=3)], area="other"))
    assert c.visit_first is False
    assert c.total == 1500


def test_unknown_area_is_a_domain_error() -> None:
    with pytest.raises(DomainError, match="area"):
        totals(quote(items=[QuoteItem(service="sofa", seats=3)], area="mombasa"))


def test_empty_basket_is_a_domain_error() -> None:
    with pytest.raises(DomainError, match="at least one"):
        totals(quote())


def test_unknown_service_and_addon_are_domain_errors() -> None:
    with pytest.raises(DomainError, match="unknown service"):
        totals(quote(items=[QuoteItem(service="jacuzzi")]))
    with pytest.raises(DomainError, match="unknown add-on"):
        totals(quote(addons=[QuoteAddon(key="helipad")]))


# ──────────────────────────────── VAT (§13a) ────────────────────────────────


def test_no_vat_line_when_not_registered() -> None:
    c = totals(quote(items=[QuoteItem(service="sofa", seats=3)]))
    assert c.vat == 0
    assert c.total == 1500


def test_vat_applies_on_top_when_registered() -> None:
    """PRICES.md §J: flyer prices are final for a non-VAT business; VAT is ON TOP."""
    c = totals(
        quote(
            items=[
                QuoteItem(service="sofa", seats=3),
                QuoteItem(service="mattress", size="5x6"),
            ],
            addons=[QuoteAddon(key="fridge")],
        ),
        vat_registered=True,
    )
    assert c.subtotal == 3800
    assert c.vat == 608  # 3,800 x 16%
    assert c.total == 4408
