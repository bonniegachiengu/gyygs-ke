"""What the operator can do that a customer cannot — §3b/§3c.

Per-item notes, flags and tags; ad-hoc lines the catalogue has no entry for;
and a manual override on an engine-priced line, for after a site visit or the
morning of the clean.

The load-bearing tests here are the ones proving this is a NARROW, AUDITED
exception rather than a hole in server-authoritative pricing: the customer lane
cannot reach any of it, and every deviation names itself in the change log.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_quote_limiter
from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter
from app.main import create_app

PIN = "test-pin-9999"
HDR = {"X-Admin-PIN": PIN}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PIN", PIN)
    monkeypatch.setenv("LEAD_DB_PATH", str(tmp_path / "leads.db"))
    monkeypatch.setenv("LEAD_STORE", "sqlite")
    monkeypatch.setenv("DEPOSIT_PCT", "30")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_quote_limiter] = lambda: SlidingWindowLimiter(10_000, 10_000)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


BASE = {
    "addons": [], "area": "nairobi",
    "preferred": {"day": "2026-09-01", "window": "morning"},
    "contact": {"name": "Superpowers"}, "recurring": False,
}


def new_job(client, items=None):
    r = client.post("/api/admin/quotes", headers=HDR,
                    json={**BASE, "items": items or [{"service": "sofa", "seats": 3}]})
    assert r.status_code == 200, r.text
    return r.json()["quote_ref"]


def job(client, ref):
    return client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()


def changes(client, ref):
    return client.get(f"/api/admin/jobs/{ref}/changes", headers=HDR).json()["changes"]


class TestCustomLines:
    def test_a_custom_line_raises_the_total_by_exactly_its_amount(self, client):
        ref = new_job(client)                       # sofa 3 seats = 1,500
        before = job(client, ref)["total_cents"]
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "addons": [],
            "reason": "after the visit",
            "operator": {"custom_lines": [
                {"label": "Chandelier crystals", "amount": 3500, "note": "by hand"}]},
        })
        assert r.status_code == 200, r.text
        assert r.json()["new_total_cents"] == before + 350_000

    def test_the_custom_line_names_itself_in_the_log(self, client):
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "addons": [],
            "operator": {"custom_lines": [{"label": "Chandelier crystals", "amount": 3500}]},
        })
        detail = changes(client, ref)[-1]["detail"]
        assert "Chandelier crystals" in detail and "3,500" in detail


class TestPriceOverride:
    def _line(self, client, ref):
        basket = json.loads(job(client, ref)["items"])
        return basket

    def test_an_override_moves_the_total_by_the_delta(self, client):
        ref = new_job(client)                       # Sofa — 3 seats : 1,500
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "addons": [],
            "reason": "far worse than described",
            "operator": {"overrides": [
                {"index": 0, "label": "Sofa — 3 seats", "amount": 2500,
                 "reason": "pet hair throughout"}]},
        })
        assert r.status_code == 200, r.text
        assert r.json()["new_total_cents"] == 250_000

    def test_the_override_names_itself_in_the_log(self, client):
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "addons": [],
            "operator": {"overrides": [
                {"index": 0, "label": "Sofa — 3 seats", "amount": 2500,
                 "reason": "pet hair throughout"}]},
        })
        detail = changes(client, ref)[-1]["detail"]
        assert "1,500" in detail and "2,500" in detail and "pet hair" in detail

    def test_a_stale_override_is_refused_and_the_job_is_untouched(self, client):
        """The guard that matters. If the basket moved underneath the override,
        applying it by index would reprice a line nobody chose."""
        ref = new_job(client)
        before = job(client, ref)["total_cents"]
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            # the basket is now curtains, but the override still names the sofa
            "items": [{"service": "curtains", "size": "sheers", "qty": 2}], "addons": [],
            "operator": {"overrides": [
                {"index": 0, "label": "Sofa — 3 seats", "amount": 9999}]},
        })
        assert r.status_code == 400
        assert "basket changed" in r.json()["detail"]
        assert job(client, ref)["total_cents"] == before

    def test_an_override_past_the_end_is_refused(self, client):
        ref = new_job(client)
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "addons": [],
            "operator": {"overrides": [
                {"index": 7, "label": "Sofa — 3 seats", "amount": 100}]},
        })
        assert r.status_code == 400
        assert "no longer exists" in r.json()["detail"]

    def test_an_override_equal_to_the_auto_price_is_not_logged_as_a_change(self, client):
        """Opening the override field and typing the number already shown is not
        a deviation, and should not read as one in the history."""
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "addons": [], "reason": "no change",
            "operator": {"overrides": [
                {"index": 0, "label": "Sofa — 3 seats", "amount": 1500}]},
        })
        assert changes(client, ref)[-1]["detail"] == "no change"


class TestPerItemDetail:
    """Notes, flags and tags ride in the raw item dicts. QuoteItem is
    extra="ignore", so validating them away is the easy accidental bug."""

    def test_a_per_item_note_and_flags_survive_storage(self, client):
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3,
                       "note": "handle the silk cushions gently",
                       "flags": ["fragile", "extra_dirty"],
                       "tags": ["upstairs"]}],
            "addons": [],
        })
        stored = json.loads(job(client, ref)["items"])["items"][0]
        assert stored["note"] == "handle the silk cushions gently"
        assert stored["flags"] == ["fragile", "extra_dirty"]
        assert stored["tags"] == ["upstairs"]

    def test_per_item_detail_does_not_change_the_price(self, client):
        ref = new_job(client)
        before = job(client, ref)["total_cents"]
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3, "flags": ["urgent"],
                       "note": "ring twice"}],
            "addons": [],
        }).json()
        assert r["new_total_cents"] == before


class TestTheCustomerLaneCannotReachAnyOfThis:
    def test_a_customer_cannot_send_a_custom_line(self, client):
        plain = client.post("/api/quote", json={**BASE, "items": [{"service": "sofa", "seats": 3}]}).json()
        sneaky = client.post("/api/quote", json={
            **BASE, "items": [{"service": "sofa", "seats": 3}],
            "operator": {"custom_lines": [{"label": "free money", "amount": -0}]},
        }).json()
        assert sneaky["total"] == plain["total"]

    def test_a_customer_cannot_override_a_line(self, client):
        plain = client.post("/api/quote", json={**BASE, "items": [{"service": "sofa", "seats": 3}]}).json()
        sneaky = client.post("/api/quote", json={
            **BASE, "items": [{"service": "sofa", "seats": 3}],
            "operator": {"overrides": [{"index": 0, "label": "Sofa — 3 seats", "amount": 1}]},
        }).json()
        assert sneaky["total"] == plain["total"]
        assert sneaky["total"] > 1

    def test_operator_extras_still_need_the_pin(self, client):
        ref = new_job(client)
        r = client.post(f"/api/admin/jobs/{ref}/reprice", json={
            "items": [{"service": "sofa", "seats": 3}], "addons": [],
            "operator": {"custom_lines": [{"label": "x", "amount": 1}]},
        })
        assert r.status_code == 401
