"""Pydantic models — the API contract.

Field names here ARE the contract (ARCHITECTURE.md §5). The frontend consumes them
through a generated TypeScript client, so renaming a field is a breaking change that
must go through the spec first.

Two halves:
  * the catalogue (`GET /api/pricing`) — what the customer may choose
  * the quote (`POST /api/quote`)      — what they chose, and what it costs
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

# `from` is a Python keyword, so the field is `from_` with a serialisation alias.
# populate_by_name lets code construct with `from_=...` while JSON shows "from".
_ALIASED = ConfigDict(populate_by_name=True, serialize_by_alias=True)

Strategy = Literal["per_unit", "tier", "size_tier", "flat", "visit"]
Window = Literal["morning", "afternoon"]

# ─────────────────────────────── catalogue ───────────────────────────────


class Tier(BaseModel):
    """One fixed-price option: a house size, or a carpet/mattress ft size."""

    key: str
    label: str
    price: int


class ExtraDef(BaseModel):
    """A priced add-on attached to a service (extra bedroom, dining chair)."""

    key: str
    label: str
    price: int
    per: Literal["unit"] = "unit"


class Modifier(BaseModel):
    """An additive surcharge on a line (carpet thick/shaggy).

    ARCHITECTURE §6 describes modifiers as multiplicative — "strategy result x
    (1 + modifiers)" — but its own §5 data says `add_range: [300, 500]` and
    PRICES.md §F says "+ KSh 300 - 500". Additive wins: the source of truth and
    the concrete data agree against one line of loose prose. The two happen to
    coincide on a 5x7 carpet (1000 + 300 == 1000 * 1.3), which is exactly how
    this would ship unnoticed, so the test asserts on a 6x9 instead.
    """

    model_config = _ALIASED

    key: str
    label: str
    add: int | None = None
    # A 2-element list rather than tuple[int, int]: openapi-typescript renders a
    # tuple as [number, number] in one position and number[] in another, which
    # makes the generated client fail to typecheck against itself.
    add_range: Annotated[list[int], Field(min_length=2, max_length=2)] | None = None


class AboveDef(BaseModel):
    """The open-ended top of a size ladder (mattress "6x7 & above")."""

    model_config = _ALIASED

    key: str
    label: str
    price: int
    from_: bool = Field(True, alias="from")


class Service(BaseModel):
    model_config = _ALIASED

    key: str
    label: str
    strategy: Strategy

    # tier / size_tier
    tiers: list[Tier] | None = None
    extra: ExtraDef | None = None  # house: extra_bedroom beyond 4BR
    above: AboveDef | None = None  # mattress: 6x7_plus
    larger: Literal["visit"] | None = None  # carpet: larger sizes are quoted on a visit
    modifiers: list[Modifier] | None = None

    # per_unit
    unit: str | None = None
    rate: int | None = None
    min_units: int | None = None
    max_units: int | None = None
    extras: list[ExtraDef] | None = None  # sofa: dining / office chairs

    # visit
    from_: int | None = Field(None, alias="from")

    # UX hints — QUOTE_CALCULATOR_SPEC §5 Step 1
    icon: str | None = None
    from_label: int | None = None
    free_text: bool = False


class Addon(BaseModel):
    model_config = _ALIASED

    key: str
    label: str
    price: int | None = None
    # See Modifier.add_range for why this is a list, not a tuple.
    price_range: Annotated[list[int], Field(min_length=2, max_length=2)] | None = None
    per: Literal["unit"] | None = None
    from_: bool = Field(False, alias="from")


class Area(BaseModel):
    key: str
    label: str
    # True means "confirm we cover you" — a coverage question, NOT a pricing one.
    # It must never set visit_first: ARCHITECTURE §5 scopes that to items ("true if
    # any item is visit/quote/from") and QUOTE_CALCULATOR_SPEC §9 says an "Other"
    # area proceeds with a note. Otherwise a plain 3-seat sofa would lose its price
    # merely because the customer lives in Athi River.
    visit: bool = False


class Rules(BaseModel):
    recurring_discount_pct: int
    transport: Literal["separate"] = "separate"
    # False: premises type decides the site-visit branch, so a residential repeat
    # customer still gets a real total. See CLAUDE.md.
    recurring_requires_visit: bool = False
    # The repeat discount is EARNED, not claimed. It applies from this job number
    # onward — 2 means "full price on the first clean, discount from the second".
    # 1 would restore the old behaviour (discount on a self-declared checkbox,
    # first job, no commitment). Decided by Bonnie + Mercy, 16 Aug 2026.
    recurring_discount_from_job: int = 2


class PricingCatalogue(BaseModel):
    version: str
    currency: str
    minimum_callout: int
    services: list[Service]
    addons: list[Addon]
    areas: list[Area]
    rules: Rules


# ──────────────────────────────── request ────────────────────────────────


class QuoteItemExtra(BaseModel):
    key: str
    qty: Annotated[int, Field(ge=1, le=50)] = 1


class SiteVisitDetails(BaseModel):
    """QUOTE_CALCULATOR_SPEC §5.7 — collected instead of an instant total."""

    premises_type: str | None = Field(None, max_length=60)
    rough_size: str | None = Field(None, max_length=120)
    frequency: Literal["one_off", "weekly", "fortnightly", "monthly"] | None = None


class QuoteItem(BaseModel):
    # "ignore", not "forbid": a client that posts its own `total` gets it silently
    # dropped, which is the guardrail. "forbid" would 422 and make the client
    # brittle to evolve.
    model_config = ConfigDict(extra="ignore")

    service: str
    tier: str | None = None  # house: "2br"
    size: str | None = None  # carpet / mattress: "5x6" | "larger" | "6x7_plus"
    seats: Annotated[int, Field(ge=1, le=9)] | None = None  # sofa
    qty: Annotated[int, Field(ge=1, le=50)] = 1
    extra_bedrooms: Annotated[int, Field(ge=0, le=10)] = 0
    modifiers: list[str] = Field(default_factory=list)
    extras: list[QuoteItemExtra] = Field(default_factory=list)
    note: str | None = Field(None, max_length=500)  # "Something else" free text


class QuoteAddon(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    qty: Annotated[int, Field(ge=1, le=50)] = 1


class Preferred(BaseModel):
    day: date | None = None
    window: Window | None = None


class Contact(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def normalise_kenyan_mobile(cls, v: str | None) -> str | None:
        """Accept 07xx / 01xx / +2547xx / 2547xx; store as 2547xxxxxxxx."""
        if v is None:
            return None
        raw = "".join(ch for ch in v if ch.isdigit() or ch == "+")
        digits = raw.lstrip("+")
        if digits.startswith("254"):
            national = digits[3:]
        elif digits.startswith("0"):
            national = digits[1:]
        else:
            national = digits
        if len(national) != 9 or national[0] not in {"7", "1"}:
            raise ValueError("enter a Kenyan mobile number, e.g. 0716 869 648")
        return f"254{national}"


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[QuoteItem] = Field(default_factory=list)
    addons: list[QuoteAddon] = Field(default_factory=list)
    area: str
    preferred: Preferred | None = None
    contact: Contact
    recurring: bool = False

    # ARCHITECTURE §13a — eTIMS-ready, not eTIMS-integrated.
    business_name: str | None = Field(None, max_length=120)
    kra_pin: str | None = Field(None, max_length=20)

    site_visit: SiteVisitDetails | None = None


# ──────────────────────────────── response ───────────────────────────────


class QuoteLine(BaseModel):
    """Exactly the §5 shape — {label, amount}. Do not add keys."""

    label: str
    amount: int


class QuoteResponse(BaseModel):
    quote_ref: str
    currency: str = "KSh"
    lines: list[QuoteLine]
    subtotal: int
    discount: int
    total: int
    visit_first: bool
    transport_note: str
    whatsapp_url: str
    created_at: datetime

    # Additive, both None under the default config (VAT_REGISTERED=false and no
    # business_name), so the default wire format matches the §5 example exactly.
    vat: int | None = None
    etims_note: str | None = None

    @field_serializer("created_at")
    def _utc_z(self, dt: datetime) -> str:
        # §5 shows "2026-08-12T09:00:00Z"; Pydantic would emit "+00:00".
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
