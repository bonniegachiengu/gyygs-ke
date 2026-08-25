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


def test_no_price_floor_by_default() -> None:
    """Mercy, 16 Aug 2026: "don't cap the price, no 1000 or 1500 or any other cap."

    The flyer's numbers are the numbers. A single microwave is 400 and quotes at
    400 — nothing silently rounds a small job up.
    """
    c = totals(quote(addons=[QuoteAddon(key="microwave")]))
    assert c.subtotal == 400
    assert c.total == 400
    assert c.minimum_applied is False
    assert c.minimum_adjustment == 0
    assert sum(line.amount for line in c.lines) == c.subtotal


@pytest.mark.parametrize(
    ("service", "kwargs", "price"),
    [
        ("sofa", {"seats": 1}, 500),
        ("sofa", {"seats": 2}, 1000),
        ("mattress", {"size": "3x6"}, 1000),
        ("carpet", {"size": "3x5"}, 500),
    ],
)
def test_small_jobs_quote_at_their_flyer_price(service: str, kwargs: dict, price: int) -> None:
    """Every one of these used to be repriced upward by the 1,500 floor."""
    c = totals(quote(items=[QuoteItem(service=service, **kwargs)]))
    assert c.total == price


def test_floor_mechanism_still_works_if_it_is_ever_switched_back_on() -> None:
    """Kept, not deleted — a floor is a config change, not a code change."""
    cat = build_catalogue(minimum_callout=1500)
    c = compute_quote(quote(addons=[QuoteAddon(key="microwave")]), cat)
    assert c.total == 1500
    assert c.minimum_applied is True
    assert c.minimum_adjustment == 1100
    # Shown as its own row under the subtotal, never folded into an item line —
    # so the itemised card still adds up to the subtotal.
    assert sum(line.amount for line in c.lines) == c.subtotal


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


def test_single_seat_is_charged_per_seat() -> None:
    """PRICES.md §E's own note is "Price is per seat (1 seat)" — its table just
    starts at a 2-seater, which was never a stated minimum. Part of Mercy's
    "no cap of any kind"."""
    c = totals(quote(items=[QuoteItem(service="sofa", seats=1)]))
    assert c.subtotal == 500
    assert c.lines[0].label == "Sofa — 1 seat"


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


# ── the repeat discount is EARNED, not claimed (Bonnie + Mercy, 16 Aug 2026) ──


def test_ticking_recurring_does_not_discount_the_first_job() -> None:
    """The headline rule. `recurring` is intent; it never moves the price.

    Before this, anyone could tick "I'd like this regularly" and take 10% off a
    one-off job on their first booking, having promised nothing. At a 50-55%
    gross margin that is ~20% of the margin, handed to someone who may never
    come back — and the customer most likely to hunt for the checkbox is the
    price-sensitive one-off.
    """
    c = totals(quote(items=[QuoteItem(service="house", tier="2br")], recurring=True))
    assert c.subtotal == 5000
    assert c.discount == 0
    assert c.total == 5000


def test_repeat_customer_earns_the_discount() -> None:
    """What Phase 3's booking flow will set once a second job is real."""
    c = totals(
        quote(items=[QuoteItem(service="house", tier="2br")], recurring=True),
        repeat_customer=True,
    )
    assert c.subtotal == 5000
    assert c.discount == 500
    assert c.total == 4500


def test_repeat_discount_does_not_need_the_recurring_flag() -> None:
    """A returning customer is a returning customer, checkbox or not."""
    c = totals(quote(items=[QuoteItem(service="house", tier="2br")]), repeat_customer=True)
    assert c.discount == 500


def test_catalogue_states_which_job_the_discount_starts_on() -> None:
    """The frontend builds its promise copy from this rather than hardcoding it."""
    assert CAT.rules.recurring_discount_from_job == 2
    assert CAT.rules.recurring_discount_pct == 10


def test_repeat_discount_floors_to_whole_shillings() -> None:
    # 4,150 x 10% = 415.0; use a basket that would otherwise land on a half.
    c = totals(
        quote(
            items=[QuoteItem(service="mattress", size="5x6")],
            addons=[QuoteAddon(key="windows_inside", qty=15), QuoteAddon(key="microwave")],
        ),
        repeat_customer=True,
    )
    assert c.subtotal == 1500 + 2250 + 400
    assert c.discount == c.subtotal * 10 // 100  # integer floor, never a fraction


def test_recurring_discount_then_the_minimum_floor() -> None:
    """Pins ARCHITECTURE §6 over QUOTE_CALCULATOR_SPEC §6, for the day a floor
    is ever switched back on.

    §6 of the tech contract compares the floor against the DISCOUNTED value; the
    UX spec's summary compares it against the raw subtotal. They only differ
    here: 1,600 - 10% = 1,440, which is under a 1,500 floor.
    """
    cat = build_catalogue(minimum_callout=1500)
    c = compute_quote(quote(addons=[QuoteAddon(key="bathroom", qty=2)]), cat, repeat_customer=True)
    assert c.subtotal == 1600
    assert c.discount == 160
    assert c.total == 1500  # not 1,440, and not 1,600


def test_residential_recurring_still_gets_a_real_total() -> None:
    """Premises decides the visit branch, not the recurring flag."""
    c = totals(quote(items=[QuoteItem(service="house", tier="2br")], recurring=True))
    assert c.visit_first is False
    assert c.total == 5000


def test_repeat_discount_is_visible_on_a_small_basket() -> None:
    """Regression guard for the bug that removing the price floor fixed.

    A 3-seat sofa is 1,500. Under the old 1,500 call-out floor, -10% took it to
    1,350 and the floor pushed it straight back to 1,500 — so the repeat rate
    was invisible on every job under ~1,667, which included the single most
    common basket in the specs. With no floor it simply shows.
    """
    c = totals(quote(items=[QuoteItem(service="sofa", seats=3)]), repeat_customer=True)
    assert c.subtotal == 1500
    assert c.discount == 150
    assert c.total == 1350
    assert c.minimum_applied is False


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


def test_transport_is_its_own_row_never_an_item_line() -> None:
    """MYRAH_OPERATIONS_DESIGN.md §3d moved transport INTO the quote.

    It is still not an ITEM line: `sum(lines) == subtotal` is load-bearing (the
    §5 response shape and the operator override both index into `lines`), so
    travel rides alongside like the call-out floor does, not inside.
    """
    basket = dict(
        items=[QuoteItem(service="sofa", seats=3)],
        addons=[QuoteAddon(key="fridge")],
    )
    c = totals(quote(**basket), transport=300)
    assert sum(line.amount for line in c.lines) == c.subtotal
    assert not any("transport" in line.label.lower() for line in c.lines)
    assert c.transport == 300


def test_transport_raises_the_total_by_exactly_the_fee() -> None:
    basket = dict(items=[QuoteItem(service="sofa", seats=3)])
    without = totals(quote(**basket))
    with_fee = totals(quote(**basket), transport=450)
    assert with_fee.total == without.total + 450


def test_the_repeat_discount_never_erodes_transport() -> None:
    """The discount is a thank-you on Myrah's LABOUR. Discounting her fuel would
    quietly cut a cost she pays either way."""
    basket = dict(items=[QuoteItem(service="sofa", seats=6)])
    plain = totals(quote(**basket), transport=500, repeat_customer=True)
    no_transport = totals(quote(**basket), repeat_customer=True)
    assert plain.total - no_transport.total == 500, "the fee was discounted"


def test_zero_transport_behaves_exactly_like_before() -> None:
    """An unset zone must be indistinguishable from the old no-transport world,
    so the mechanism can ship before Mercy has set a single number."""
    basket = dict(items=[QuoteItem(service="sofa", seats=3)])
    assert totals(quote(**basket), transport=0).total == totals(quote(**basket)).total


def test_the_note_no_longer_claims_transport_is_separate() -> None:
    assert "separate" not in TRANSPORT_NOTE.lower()
    assert "included" in TRANSPORT_NOTE.lower()


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


# ── F2 · Curtains, per piece ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("size", "price"),
    [("sheers", 300), ("standard", 400), ("large", 600), ("very_large", 1000)],
)
def test_curtain_types(size: str, price: int) -> None:
    c = totals(quote(items=[QuoteItem(service="curtains", size=size)]))
    assert c.subtotal == price
    assert c.total == price
    assert c.visit_first is False, "every curtain type has a hard price"


def test_curtains_are_priced_per_piece() -> None:
    """PRICES.md F2: per panel, not per window. Four standard panels is 1,600."""
    c = totals(quote(items=[QuoteItem(service="curtains", size="standard", qty=4)]))
    assert c.subtotal == 1600
    assert c.lines[0].label == "Curtains — Standard ×4"


def test_curtains_mix_with_the_rest_of_a_basket() -> None:
    c = totals(
        quote(
            items=[
                QuoteItem(service="curtains", size="sheers", qty=2),
                QuoteItem(service="curtains", size="very_large", qty=1),
                QuoteItem(service="sofa", seats=3),
            ]
        )
    )
    assert c.subtotal == 600 + 1000 + 1500
    assert c.visit_first is False


def test_curtain_tiers_carry_no_ft_suffix() -> None:
    """Guards the UI: carpet and mattress chips read "5x7 ft", curtains must not
    read "Sheers ft". The suffix is catalogue data, not a frontend assumption."""
    by_key = {s.key: s for s in CAT.services}
    assert by_key["curtains"].tier_unit is None
    assert by_key["carpet"].tier_unit == "ft"
    assert by_key["mattress"].tier_unit == "ft"


def test_curtains_match_the_price_list() -> None:
    """Transcribed straight from PRICES.md F2."""
    expected = {"sheers": 300, "standard": 400, "large": 600, "very_large": 1000}
    curtains = next(s for s in CAT.services if s.key == "curtains")
    assert {t.key: t.price for t in curtains.tiers or []} == expected
