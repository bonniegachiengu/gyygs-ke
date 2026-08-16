"""The catalogue — the in-code mirror of PRICES.md.

**PRICES.md is the human source of truth. Update it first, then this module.**
`tests/test_pricing_catalogue_matches_prices_md.py` transcribes the flyer's tables
independently and asserts against what is built here, so an edit in one place
without the other fails the suite.

Section letters in the comments below refer to PRICES.md's own headings.
"""

from __future__ import annotations

from app.domain.models import (
    AboveDef,
    Addon,
    Area,
    ExtraDef,
    Modifier,
    PricingCatalogue,
    Rules,
    Service,
    Tier,
)

#: Bump whenever PRICES.md changes. Surfaces in GET /api/pricing.
PRICING_VERSION = "2026-08-12"
CURRENCY = "KSh"

# ── A · House deep cleaning, by bedrooms ──────────────────────────────────
HOUSE = Service(
    key="house",
    label="Whole-house deep clean",
    strategy="tier",
    icon="🏠",
    from_label=2500,
    tiers=[
        Tier(key="studio", label="Studio / Bedsitter", price=2500),
        Tier(key="1br", label="1 Bedroom", price=3500),
        Tier(key="2br", label="2 Bedroom", price=5000),
        Tier(key="3br", label="3 Bedroom", price=6500),
        Tier(key="4br", label="4 Bedroom", price=8000),
    ],
    # "Extra bedroom (each beyond 4) +1,500"
    extra=ExtraDef(key="extra_bedroom", label="Extra bedroom", price=1500),
)

# ── E · Sofa, per seat (~KSh 500/seat; the 2-seater at 1,000 is the floor) ──
SOFA = Service(
    key="sofa",
    label="Sofa",
    strategy="per_unit",
    icon="🛋",
    from_label=1000,
    unit="seat",
    rate=500,
    min_units=2,
    max_units=9,  # PRICES.md §E stops at a 9-seater
    extras=[
        ExtraDef(key="dining_chair", label="Dining chair", price=250),
        ExtraDef(key="office_chair", label="Office chair", price=350),
    ],
)

# ── F · Carpet, by ft size. Larger sizes are quoted on a visit. ────────────
CARPET = Service(
    key="carpet",
    label="Carpet / Rug",
    strategy="size_tier",
    icon="🧶",
    from_label=500,
    tiers=[
        # Labels carry no spaces around the ×: QUOTE_CALCULATOR_SPEC §3 and §7
        # print lines as "Mattress — 5×6", and the label composes straight into both.
        Tier(key="3x5", label="3×5", price=500),
        Tier(key="4x6", label="4×6", price=700),
        Tier(key="5x7", label="5×7", price=1000),
        Tier(key="6x9", label="6×9", price=1300),
        Tier(key="8x10", label="8×10", price=1800),
        Tier(key="9x12", label="9×12", price=2200),
        Tier(key="10x14", label="10×14", price=2800),
    ],
    larger="visit",
    # "Thick / shaggy carpets: + KSh 300 - 500" — a range, so it also makes the
    # quote visit-first (PRICES.md, Calculator handling rules).
    modifiers=[Modifier(key="thick_shaggy", label="Thick / shaggy", add_range=(300, 500))],
)

# ── G · Mattress, by ft size ──────────────────────────────────────────────
MATTRESS = Service(
    key="mattress",
    label="Mattress",
    strategy="size_tier",
    icon="🛏",
    from_label=1000,
    tiers=[
        Tier(key="3x6", label="3×6", price=1000),
        Tier(key="4x6", label="4×6", price=1200),
        Tier(key="5x6", label="5×6", price=1500),
        Tier(key="6x6", label="6×6", price=1800),
    ],
    above=AboveDef(key="6x7_plus", label="6×7 & above", price=2000, from_=True),
)

# ── D · Post-construction / heavy-duty — always a site visit ──────────────
POST_CONSTRUCTION = Service(
    key="post_construction",
    label="Post-construction",
    strategy="visit",
    icon="🧱",
    from_=10000,
)

# ── Two cards QUOTE_CALCULATOR_SPEC §5 Step 1 requires that ARCHITECTURE §5's
#    services array omits. Both route to the site-visit branch (§5.7). ───────
COMMERCIAL = Service(
    key="commercial",
    label="Office / commercial",
    strategy="visit",
    icon="🏢",
)

SOMETHING_ELSE = Service(
    key="other",
    label="Something else",
    strategy="visit",
    icon="❓",
    free_text=True,
)

SERVICES: list[Service] = [
    SOFA,
    CARPET,
    MATTRESS,
    HOUSE,
    COMMERCIAL,
    POST_CONSTRUCTION,
    SOMETHING_ELSE,
]

# ── B · House add-ons · C · Decluttering ──────────────────────────────────
# PRICES.md §H repeats fridge/oven/microwave/rust/grease/decluttering from §B and
# §C — it is the flyer's second page, not extra services. Modelling it separately
# would double-count, so it is deliberately absent.
ADDONS: list[Addon] = [
    Addon(key="kitchen_deep", label="Kitchen deep clean", price=1500),
    Addon(key="bathroom", label="Bathroom / Toilet", price=800, per="unit"),
    Addon(key="windows_inside", label="Windows (inside)", price=150, per="unit"),
    Addon(key="fridge", label="Fridge", price=800),
    Addon(key="oven", label="Oven", price=800),
    Addon(key="microwave", label="Microwave", price=400),
    Addon(key="balcony", label="Balcony", price=500),
    # A range, so visit-first; contributes its lower bound.
    Addon(key="inside_cabinets", label="Inside cabinets", price_range=(500, 1000)),
    Addon(key="wall_spot", label="Wall spot cleaning", price=500, from_=True),
    Addon(key="rust", label="Rust stain removal", price=500, from_=True),
    Addon(key="grease", label="Heavy grease removal", price=500, from_=True),
    # §C light decluttering is a flat 500 with no "from" (ARCHITECTURE §5 agrees);
    # §H's "Decluttering & Organising — from 500" is the looser page-2 restatement.
    Addon(key="declutter_light", label="Light decluttering", price=500),
    Addon(key="declutter_room", label="Full-room decluttering", price=1000, from_=True),
    Addon(key="declutter_house", label="Whole-house decluttering", price=2500, from_=True),
]

# ── Areas. ARCHITECTURE §5 gives only `nairobi` a label; the rest are supplied
#    here because the UI renders chips and the WhatsApp text prints "Area: Ruiru".
AREAS: list[Area] = [
    Area(key="nairobi", label="Nairobi & suburbs"),
    Area(key="ruiru", label="Ruiru"),
    Area(key="thika", label="Thika"),
    Area(key="juja", label="Juja"),
    Area(key="kiambu", label="Kiambu"),
    Area(key="other", label="Other", visit=True),
]


def build_catalogue(
    *,
    minimum_callout: int = 1500,
    recurring_discount_pct: int = 10,
    recurring_requires_visit: bool = False,
) -> PricingCatalogue:
    """Assemble the catalogue. The three rule values come from config so a
    business decision (Mercy's Friday calls) is a config change, not a deploy."""
    return PricingCatalogue(
        version=PRICING_VERSION,
        currency=CURRENCY,
        minimum_callout=minimum_callout,
        services=SERVICES,
        addons=ADDONS,
        areas=AREAS,
        rules=Rules(
            recurring_discount_pct=recurring_discount_pct,
            transport="separate",
            recurring_requires_visit=recurring_requires_visit,
        ),
    )


#: Default catalogue — used by tests and as the engine's default argument.
CATALOGUE = build_catalogue()


# ── Lookup helpers (pure; the engine uses these instead of scanning lists) ──

SERVICES_BY_KEY: dict[str, Service] = {s.key: s for s in SERVICES}
ADDONS_BY_KEY: dict[str, Addon] = {a.key: a for a in ADDONS}
AREAS_BY_KEY: dict[str, Area] = {a.key: a for a in AREAS}
