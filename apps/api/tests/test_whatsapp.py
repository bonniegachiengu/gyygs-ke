"""The WhatsApp handoff text — QUOTE_CALCULATOR_SPEC.md §7, byte for byte."""

from __future__ import annotations

from datetime import date
from urllib.parse import unquote

from app.domain.models import Preferred, QuoteLine
from app.domain.whatsapp import WA_RULE, build_message, build_url, format_preferred

WORKED_EXAMPLE_LINES = [
    QuoteLine(label="Sofa — 3 seats", amount=1500),
    QuoteLine(label="Mattress — 5×6", amount=1500),
    QuoteLine(label="Add-on — Fridge", amount=800),
]


def _worked_example(**kw) -> str:
    defaults = dict(
        lines=WORKED_EXAMPLE_LINES,
        total=3800,
        quote_ref="MY-260812-014",
        area_label="Ruiru",
        site_host="myrah.vyybandasky.online",
        visit_first=False,
        preferred=Preferred(day=date(2026, 8, 15), window="morning"),  # a Saturday
        contact_name="Faith",
    )
    return build_message(**{**defaults, **kw})


def test_worked_example_matches_the_spec_template() -> None:
    assert _worked_example() == (
        "Hi Myrah Cleaning \U0001f44b I'd like to book this quote:\n"
        "\n"
        "• Sofa — 3 seats: KSh 1,500\n"
        "• Mattress — 5×6: KSh 1,500\n"
        "• Add-on — Fridge: KSh 800\n"
        "——————————————\n"
        "Estimated total: KSh 3,800\n"
        "Transport: charged separately by area\n"
        "Area: Ruiru  ·  Preferred: Sat, morning\n"
        "Name: Faith\n"
        "\n"
        "(Quote #MY-260812-014 · from myrah.vyybandasky.online)"
    )


def test_rule_is_exactly_fourteen_em_dashes() -> None:
    assert WA_RULE == "—" * 14
    assert len(WA_RULE) == 14


def test_area_line_uses_two_spaces_around_the_middot() -> None:
    assert "Area: Ruiru  ·  Preferred: Sat, morning" in _worked_example()


def test_footer_uses_single_spaces_around_the_middot() -> None:
    assert _worked_example().endswith("(Quote #MY-260812-014 · from myrah.vyybandasky.online)")


def test_preferred_clause_is_omitted_when_absent() -> None:
    msg = _worked_example(preferred=None)
    assert "Area: Ruiru\n" in msg
    assert "Preferred" not in msg


def test_day_name_is_locale_independent() -> None:
    # strftime("%a") would follow the server locale; the DOW table does not.
    assert format_preferred(Preferred(day=date(2026, 8, 15), window="morning")) == "Sat, morning"
    assert format_preferred(Preferred(day=date(2026, 8, 16))) == "Sun"
    assert format_preferred(None) is None


def test_visit_first_total_is_prefixed_from() -> None:
    msg = _worked_example(visit_first=True)
    assert "Estimated total: from KSh 3,800 (final price confirmed on a quick site visit)" in msg


def test_arithmetic_lines_appear_only_when_they_happened() -> None:
    plain = _worked_example()
    assert "Recurring discount" not in plain
    assert "Minimum call-out" not in plain
    assert "VAT" not in plain

    rich = _worked_example(
        discount=380,
        discount_pct=10,
        minimum_adjustment=0,
        vat=608,
        vat_rate=16,
    )
    assert "Recurring discount (10%): -KSh 380" in rich
    assert "VAT (16%): KSh 608" in rich


def test_minimum_callout_is_explained_rather_than_hidden() -> None:
    msg = _worked_example(total=1500, minimum_adjustment=1100, minimum_callout=1500)
    assert "Minimum call-out applied: KSh 1,500" in msg


def test_estate_rides_along_on_the_area_line() -> None:
    """Regression: the estate was captured in the UI and dropped on the floor —
    never sent, never logged, never in the message Mercy reads."""
    msg = _worked_example(area_label="Nairobi & suburbs", estate="Kasarani")
    assert "Area: Nairobi & suburbs — Kasarani  ·  Preferred: Sat, morning" in msg


def test_estate_is_omitted_when_blank() -> None:
    for blank in (None, "", "   "):
        assert "Area: Ruiru  ·" in _worked_example(estate=blank)


def test_recurring_line_states_the_rate_without_discounting_this_job() -> None:
    msg = _worked_example(recurring=True, recurring_discount_pct=10)
    assert "Estimated total: KSh 3,800" in msg  # this job is full price
    assert "Regular service: yes — I understand every clean after my first is 10% off" in msg


def test_recurring_line_absent_when_not_requested() -> None:
    assert "Regular service" not in _worked_example()


def test_other_area_adds_the_coverage_note() -> None:
    assert "We'll confirm we cover your area." in _worked_example(
        area_label="Other", area_needs_coverage_check=True
    )


def test_business_details_and_etims_note() -> None:
    msg = _worked_example(
        business_name="Kevin's BnB",
        kra_pin="A012345678Z",
        etims_note="A KRA-compliant eTIMS tax invoice will be issued on payment.",
    )
    assert "Business: Kevin's BnB · KRA PIN: A012345678Z" in msg
    assert "eTIMS tax invoice will be issued on payment" in msg


def test_url_is_percent_encoded_for_the_right_number() -> None:
    url = build_url(_worked_example(), "254716869648")
    assert url.startswith("https://wa.me/254716869648?text=")
    assert "\n" not in url
    assert "%0A" in url
    # '+' for spaces is rendered literally by some Android WhatsApp builds.
    assert "+" not in url.split("?text=", 1)[1]
    assert unquote(url.split("?text=", 1)[1]) == _worked_example()
