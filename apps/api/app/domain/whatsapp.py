"""The WhatsApp handoff message — QUOTE_CALCULATOR_SPEC.md §7.

Pure functions. The message is built SERVER-side and URL-encoded, so the customer
cannot tamper with the total on its way to Mercy (ARCHITECTURE §11).

The §7 template is reproduced byte for byte, including the 14 em-dash rule and
the double-spaced middle dot on the Area line — `test_whatsapp.py` pins both.
"""

from __future__ import annotations

from datetime import date
from typing import Final
from urllib.parse import quote as urlquote

from app.domain.models import Preferred, QuoteLine

WA_GREETING: Final[str] = "Hi Myra Cleaning \U0001f44b I'd like to book this quote:"
WA_RULE: Final[str] = "—" * 14  # exactly 14 em dashes, per §7
WA_TRANSPORT: Final[str] = "Transport: charged separately by area"

#: Locale-independent on purpose — strftime("%a") follows the server locale.
DOW: Final[tuple[str, ...]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#: Android intents have practical size limits; a silently truncated message is
#: worse than an explicit one.
MAX_URL_LEN: Final[int] = 1800


def _money(amount: int) -> str:
    return f"KSh {amount:,}"


def format_preferred(preferred: Preferred | None) -> str | None:
    """ "Sat, morning" — or None if the customer gave no preference."""
    if preferred is None or (preferred.day is None and preferred.window is None):
        return None
    parts: list[str] = []
    if preferred.day is not None:
        parts.append(_day_name(preferred.day))
    if preferred.window is not None:
        parts.append(preferred.window)
    return ", ".join(parts)


def _day_name(d: date) -> str:
    return DOW[d.weekday()]


def build_message(
    *,
    lines: list[QuoteLine],
    total: int,
    quote_ref: str,
    area_label: str,
    site_host: str,
    visit_first: bool,
    preferred: Preferred | None = None,
    contact_name: str,
    discount: int = 0,
    discount_pct: int = 0,
    minimum_adjustment: int = 0,
    minimum_callout: int = 0,
    vat: int = 0,
    vat_rate: int = 16,
    area_needs_coverage_check: bool = False,
    recurring: bool = False,
    recurring_discount_pct: int = 0,
    business_name: str | None = None,
    kra_pin: str | None = None,
    etims_note: str | None = None,
) -> str:
    out: list[str] = [WA_GREETING, ""]

    for line in lines:
        out.append(f"• {line.label}: {_money(line.amount)}")

    out.append(WA_RULE)

    # These three only appear when they actually happened, so a default-config
    # quote renders the §7 template exactly. Without them Mercy would see
    # itemised lines that do not add up to the stated total.
    if discount > 0:
        out.append(f"Recurring discount ({discount_pct}%): -{_money(discount)}")
    if minimum_adjustment > 0:
        out.append(f"Minimum call-out applied: {_money(minimum_callout)}")
    if vat > 0:
        out.append(f"VAT ({vat_rate}%): {_money(vat)}")

    if visit_first:
        out.append(
            f"Estimated total: from {_money(total)} (final price confirmed on a quick site visit)"
        )
    else:
        out.append(f"Estimated total: {_money(total)}")

    out.append(WA_TRANSPORT)

    # Two spaces either side of the middle dot, per §7.
    area_line = f"Area: {area_label}"
    pref = format_preferred(preferred)
    if pref:
        area_line += f"  ·  Preferred: {pref}"
    out.append(area_line)

    if area_needs_coverage_check:
        out.append("We'll confirm we cover your area.")

    out.append(f"Name: {contact_name}")

    # In the customer's own voice — they are the one sending this. It tells Mercy
    # to expect a return booking and states the rate she'll honour, without
    # discounting the job in front of her.
    if recurring and recurring_discount_pct > 0:
        out.append(
            f"Regular service: yes — I understand every clean after my first "
            f"is {recurring_discount_pct}% off"
        )
    elif recurring:
        out.append("Regular service: yes")

    if business_name:
        detail = f"Business: {business_name}"
        if kra_pin:
            detail += f" · KRA PIN: {kra_pin}"
        out.append(detail)
        if etims_note:
            out.append(etims_note)

    # Single spaces around the middle dot in the footer, per §7.
    out.extend(["", f"(Quote #{quote_ref} · from {site_host})"])

    return "\n".join(out)


def build_url(text: str, whatsapp_number: str) -> str:
    """`safe=""` so newlines become %0A and spaces %20 — not '+', which some
    Android WhatsApp builds render literally."""
    return f"https://wa.me/{whatsapp_number}?text={urlquote(text, safe='')}"


def build_handoff(text: str, whatsapp_number: str, *, line_count: int) -> str:
    """URL-encode, trimming the item list if the result would be over-long."""
    url = build_url(text, whatsapp_number)
    if len(url) <= MAX_URL_LEN or line_count <= 1:
        return url

    body = text.split("\n")
    keep = line_count
    while keep > 1:
        keep -= 1
        dropped = line_count - keep
        # Item lines start at index 2 (greeting, blank, then bullets).
        trimmed = body[: 2 + keep] + [f"• …and {dropped} more items"] + body[2 + line_count :]
        url = build_url("\n".join(trimmed), whatsapp_number)
        if len(url) <= MAX_URL_LEN:
            break
    return url
