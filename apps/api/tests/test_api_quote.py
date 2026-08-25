"""API tests for /api/pricing and /api/quote, against a fake repository."""

from __future__ import annotations

from app.core.config import get_settings
import json
import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app.repositories.base import Lead

WORKED_EXAMPLE = {
    "items": [
        {"service": "sofa", "seats": 3},
        {"service": "mattress", "size": "5x6", "qty": 1},
    ],
    "addons": [{"key": "fridge"}],
    "area": "ruiru",
    "preferred": {"day": "2026-08-15", "window": "morning"},
    "contact": {"name": "Faith"},
    "recurring": False,
}


# ─────────────────────────────── pricing ───────────────────────────────


def test_pricing_returns_the_catalogue(client: TestClient) -> None:
    r = client.get("/api/pricing")
    assert r.status_code == 200
    cat = r.json()

    assert cat["currency"] == "KSh"
    assert cat["minimum_callout"] == 0
    assert cat["rules"] == {
        "recurring_discount_pct": 10,
        "transport": "separate",
        "recurring_requires_visit": False,
        # Full price on the first clean, repeat rate from the second.
        "recurring_discount_from_job": 2,
        # The storefront renders this rather than a hardcoded figure, so the
        # advertised deposit and the one the gate enforces cannot drift apart.
        "deposit_pct": 30,
    }
    # The cards QUOTE_CALCULATOR_SPEC §5 Step 1 requires, plus curtains (PRICES.md F2).
    assert {s["key"] for s in cat["services"]} == {
        "sofa",
        "carpet",
        "curtains",
        "mattress",
        "house",
        "commercial",
        "post_construction",
        "other",
    }
    assert {a["key"] for a in cat["areas"]} == {
        "nairobi",
        "ruiru",
        "thika",
        "juja",
        "kiambu",
        "other",
    }
    # Every area carries a label — §5 only supplied nairobi's.
    assert all(a["label"] for a in cat["areas"])


def test_pricing_serialises_from_under_its_json_name(client: TestClient) -> None:
    cat = client.get("/api/pricing").json()
    post = next(s for s in cat["services"] if s["key"] == "post_construction")
    assert post["from"] == 10000
    assert "from_" not in post

    mattress = next(s for s in cat["services"] if s["key"] == "mattress")
    assert mattress["above"]["from"] is True


def test_catalogue_carries_the_whatsapp_number(client: TestClient, settings) -> None:
    """Served, not hardcoded in the frontend — switching the handoff number must
    be a config change plus a restart, never a rebuild."""
    assert client.get("/api/pricing").json()["whatsapp_number"] == settings.whatsapp_number


def test_handoff_number_follows_config(client: TestClient) -> None:
    """The same value drives the server-built wa.me URL, so the catalogue and the
    quote can never disagree about where a customer is sent."""
    number = client.get("/api/pricing").json()["whatsapp_number"]
    q = client.post("/api/quote", json=WORKED_EXAMPLE).json()
    assert q["whatsapp_url"].startswith(f"https://wa.me/{number}?text=")


def test_pricing_is_cacheable(client: TestClient) -> None:
    assert client.get("/api/pricing").headers["cache-control"] == "public, max-age=300"


# ──────────────────────────────── quote ────────────────────────────────


def test_worked_example_end_to_end(client: TestClient) -> None:
    r = client.post("/api/quote", json=WORKED_EXAMPLE)
    assert r.status_code == 200
    q = r.json()

    assert [(line["label"], line["amount"]) for line in q["lines"]] == [
        ("Sofa — 3 seats", 1500),
        ("Mattress — 5×6", 1500),
        ("Add-on — Fridge", 800),
    ]
    assert q["subtotal"] == 3800
    assert q["discount"] == 0
    assert q["total"] == 3800
    assert q["visit_first"] is False
    assert q["currency"] == "KSh"
    # §3d: transport is in the quote now. The worked example's zone has no fee
    # set, so the honest line is that it will be confirmed -- not a silent 0.
    assert q["transport_note"] == "Transport for your area is confirmed on WhatsApp."
    assert q["transport"] == 0
    assert re.fullmatch(r"MY-\d{6}-\d{3,}", q["quote_ref"])
    assert q["created_at"].endswith("Z")
    assert q["whatsapp_url"].startswith(f"https://wa.me/{get_settings().whatsapp_number}?text=")

    text = unquote(q["whatsapp_url"].split("?text=", 1)[1])
    assert "Estimated total: KSh 3,800" in text
    assert f"(Quote #{q['quote_ref']} · from myrah.vyybandasky.online)" in text

    # VAT is off by default, so the wire format matches the §5 example exactly.
    assert q["vat"] is None
    assert q["etims_note"] is None


def test_client_supplied_total_is_ignored(client: TestClient) -> None:
    """The core guardrail: never trust the client's number."""
    r = client.post("/api/quote", json={**WORKED_EXAMPLE, "total": 1, "subtotal": 1})
    assert r.status_code == 200
    assert r.json()["total"] == 3800


def test_quote_logs_a_lead_not_yet_sent(client: TestClient, repo) -> None:
    ref = client.post("/api/quote", json=WORKED_EXAMPLE).json()["quote_ref"]

    leads: list[Lead] = repo.list()
    assert len(leads) == 1
    lead = leads[0]
    assert lead.ref == ref
    assert lead.name == "Faith"
    assert lead.total == 3800
    assert lead.area == "ruiru"
    assert lead.preferred == "2026-08-15 morning"
    assert lead.visit_first is False
    # Drafts are logged so drop-off is visible — SPEC §8.
    assert lead.sent_to_wa is False
    assert lead.lead_id
    assert json.loads(lead.items)["items"][0]["service"] == "sofa"


def test_sent_beacon_flips_the_flag_and_is_idempotent(client: TestClient, repo) -> None:
    ref = client.post("/api/quote", json=WORKED_EXAMPLE).json()["quote_ref"]

    assert client.post(f"/api/quote/{ref}/sent").status_code == 204
    assert client.post(f"/api/quote/{ref}/sent").status_code == 204
    assert repo.list()[0].sent_to_wa is True


def test_sent_beacon_404s_for_an_unknown_ref(client: TestClient) -> None:
    assert client.post("/api/quote/MY-999999-001/sent").status_code == 404


def test_quote_refs_increment_within_a_day(client: TestClient) -> None:
    refs = [client.post("/api/quote", json=WORKED_EXAMPLE).json()["quote_ref"] for _ in range(3)]
    assert len(set(refs)) == 3
    tails = [int(r.rsplit("-", 1)[1]) for r in refs]
    assert tails == sorted(tails)


# ─────────────────────────── validation and errors ───────────────────────────


def test_missing_contact_name_is_422(client: TestClient) -> None:
    body = {**WORKED_EXAMPLE, "contact": {}}
    assert client.post("/api/quote", json=body).status_code == 422


def test_unknown_addon_is_400_not_500(client: TestClient) -> None:
    body = {**WORKED_EXAMPLE, "addons": [{"key": "helipad"}]}
    r = client.post("/api/quote", json=body)
    assert r.status_code == 400
    assert "helipad" in r.json()["detail"]


def test_empty_basket_is_400(client: TestClient) -> None:
    body = {**WORKED_EXAMPLE, "items": [], "addons": []}
    assert client.post("/api/quote", json=body).status_code == 400


@pytest.mark.parametrize("phone", ["0712", "not-a-phone", "+44 7700 900000"])
def test_invalid_phone_is_422(client: TestClient, phone: str) -> None:
    body = {**WORKED_EXAMPLE, "contact": {"name": "Faith", "phone": phone}}
    assert client.post("/api/quote", json=body).status_code == 422


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("0722000000", "254722000000"),
        ("+254722000000", "254722000000"),
        ("0110 123 456", "254110123456"),
    ],
)
def test_phone_is_normalised(client: TestClient, repo, given: str, stored: str) -> None:
    body = {**WORKED_EXAMPLE, "contact": {"name": "Faith", "phone": given}}
    assert client.post("/api/quote", json=body).status_code == 200
    assert repo.list()[0].phone == stored


# ──────────────────────────── commercial and eTIMS ────────────────────────────


def test_commercial_item_forces_visit_first(client: TestClient) -> None:
    body = {
        **WORKED_EXAMPLE,
        "items": [{"service": "commercial", "note": "3-floor office block"}],
        "addons": [],
        "site_visit": {"premises_type": "office", "frequency": "weekly"},
    }
    q = client.post("/api/quote", json=body).json()
    assert q["visit_first"] is True
    text = unquote(q["whatsapp_url"].split("?text=", 1)[1])
    assert "from KSh" in text


def test_estate_reaches_the_message_and_the_lead(client: TestClient, repo) -> None:
    """Regression: this field was collected on screen and silently discarded."""
    body = {**WORKED_EXAMPLE, "area": "nairobi", "estate": "Kasarani"}
    q = client.post("/api/quote", json=body).json()

    text = unquote(q["whatsapp_url"].split("?text=", 1)[1])
    assert "Area: Nairobi & suburbs — Kasarani" in text
    assert repo.list()[0].estate == "Kasarani"


def test_estate_is_optional(client: TestClient, repo) -> None:
    q = client.post("/api/quote", json=WORKED_EXAMPLE).json()
    assert "Area: Ruiru  ·" in unquote(q["whatsapp_url"].split("?text=", 1)[1])
    assert repo.list()[0].estate == ""


def test_recurring_is_intent_only_and_never_discounts_over_the_api(client: TestClient) -> None:
    """No route in v1 can hand out the repeat rate — there is no customer record,
    so every quote is priced as a first job."""
    q = client.post("/api/quote", json={**WORKED_EXAMPLE, "recurring": True}).json()
    assert q["discount"] == 0
    assert q["total"] == 3800

    text = unquote(q["whatsapp_url"].split("?text=", 1)[1])
    # Mercy still sees the intent, and the rate she'll honour next time.
    assert "Regular service: yes" in text
    assert "every clean after my first is 10% off" in text


def test_recurring_intent_is_logged_for_the_funnel(client: TestClient, repo) -> None:
    client.post("/api/quote", json={**WORKED_EXAMPLE, "recurring": True})
    assert json.loads(repo.list()[0].items)["recurring"] is True


def test_business_name_yields_the_etims_promise(client: TestClient) -> None:
    body = {**WORKED_EXAMPLE, "business_name": "Kevin's BnB", "kra_pin": "A012345678Z"}
    q = client.post("/api/quote", json=body).json()
    assert q["etims_note"] == "A KRA-compliant eTIMS tax invoice will be issued on payment."
    assert "KRA PIN: A012345678Z" in unquote(q["whatsapp_url"].split("?text=", 1)[1])


# ─────────────────────────────── rate limiting ───────────────────────────────


def test_quote_is_rate_limited_per_ip(client: TestClient, settings) -> None:
    for _ in range(settings.rate_limit_quote_per_min):
        assert client.post("/api/quote", json=WORKED_EXAMPLE).status_code == 200

    r = client.post("/api/quote", json=WORKED_EXAMPLE)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1


def test_rate_limit_keys_on_the_real_client_ip(client: TestClient, settings) -> None:
    """Cloudflare's CF-Connecting-IP, not the proxy's own address — otherwise one
    customer would throttle everyone behind the tunnel."""
    for _ in range(settings.rate_limit_quote_per_min):
        r = client.post("/api/quote", json=WORKED_EXAMPLE, headers={"CF-Connecting-IP": "1.1.1.1"})
        assert r.status_code == 200

    blocked = client.post(
        "/api/quote", json=WORKED_EXAMPLE, headers={"CF-Connecting-IP": "1.1.1.1"}
    )
    assert blocked.status_code == 429

    # A different customer is unaffected.
    other = client.post("/api/quote", json=WORKED_EXAMPLE, headers={"CF-Connecting-IP": "2.2.2.2"})
    assert other.status_code == 200
