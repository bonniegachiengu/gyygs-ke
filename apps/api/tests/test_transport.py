"""Transport by location — MYRAH_OPERATIONS_DESIGN.md §3d.

The point of the whole change is the last class in this file: **the deposit must
be computed on the total INCLUDING transport.**

The 30% deposit exists to cover Mercy's pre-work costs — the site visit and the
day-of trip. A deposit taken on the cleaning subtotal alone under-covers the
exact spend it exists to protect, which is the bug this feature fixes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_quote_limiter
from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter
from app.main import create_app

PIN = "test-pin-9999"
HDR = {"X-Admin-PIN": PIN}

BASE = {
    "addons": [], "area": "ruiru",
    "preferred": {"day": "2026-09-01", "window": "morning"},
    "contact": {"name": "Transport"}, "recurring": False,
}
SOFA = [{"service": "sofa", "seats": 3}]        # KSh 1,500


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


def set_fee(client, area, fee):
    r = client.put(f"/api/admin/transport/{area}", headers=HDR, json={"fee": fee})
    assert r.status_code == 200, r.text
    return r


class TestZonesAreDataNotCode:
    def test_zones_are_seeded_for_every_area(self, client):
        zones = client.get("/api/admin/transport", headers=HDR).json()["zones"]
        keys = {z["area_key"] for z in zones}
        areas = {a["key"] for a in client.get("/api/pricing").json()["areas"]}
        assert areas <= keys, "an area with no zone row could never be given a fee"

    def test_they_ship_at_zero_not_at_a_guess(self, client):
        zones = client.get("/api/admin/transport", headers=HDR).json()["zones"]
        assert all(z["fee"] == 0 for z in zones), (
            "a fee nobody chose must never be charged to a real client")

    def test_mercy_can_set_one(self, client):
        set_fee(client, "ruiru", 400)
        zones = {z["area_key"]: z["fee"]
                 for z in client.get("/api/admin/transport", headers=HDR).json()["zones"]}
        assert zones["ruiru"] == 400

    def test_a_fee_cannot_be_negative(self, client):
        r = client.put("/api/admin/transport/ruiru", headers=HDR, json={"fee": -50})
        assert r.status_code == 422

    def test_an_unknown_zone_is_a_404(self, client):
        assert client.put("/api/admin/transport/atlantis", headers=HDR,
                          json={"fee": 100}).status_code == 404

    def test_editing_zones_needs_the_pin(self, client):
        assert client.get("/api/admin/transport").status_code == 401
        assert client.put("/api/admin/transport/ruiru", json={"fee": 1}).status_code == 401

    def test_the_fee_reaches_the_public_catalogue(self, client):
        set_fee(client, "thika", 700)
        areas = {a["key"]: a for a in client.get("/api/pricing").json()["areas"]}
        assert areas["thika"]["transport"] == 700


class TestItIsInTheQuote:
    def test_transport_raises_the_total_by_exactly_the_fee(self, client):
        before = client.post("/api/quote", json={**BASE, "items": SOFA}).json()["total"]
        set_fee(client, "ruiru", 400)
        after = client.post("/api/quote", json={**BASE, "items": SOFA}).json()
        assert after["total"] == before + 400
        assert after["transport"] == 400

    def test_a_different_area_charges_its_own_fee(self, client):
        set_fee(client, "ruiru", 400)
        set_fee(client, "thika", 900)
        r = client.post("/api/quote", json={**BASE, "items": SOFA, "area": "thika"}).json()
        assert r["transport"] == 900

    def test_an_unset_zone_quotes_exactly_as_before(self, client):
        r = client.post("/api/quote", json={**BASE, "items": SOFA}).json()
        assert r["transport"] == 0
        assert r["total"] == 1500
        assert "confirmed on WhatsApp" in r["transport_note"]

    def test_both_lanes_charge_the_same_transport(self, client):
        """The operator board and the calculator must not disagree about travel
        any more than they may disagree about a sofa."""
        set_fee(client, "ruiru", 400)
        customer = client.post("/api/quote", json={**BASE, "items": SOFA}).json()
        operator = client.post("/api/admin/quotes", headers=HDR,
                               json={**BASE, "items": SOFA}).json()
        assert operator["total"] == customer["total"]


class TestTheDepositCoversThePreWork:
    """★ The reason this feature exists."""

    def test_the_deposit_is_computed_on_the_total_including_transport(self, client):
        set_fee(client, "ruiru", 500)
        job = client.post("/api/admin/quotes", headers=HDR,
                          json={**BASE, "items": SOFA}).json()["job"]
        # 1,500 cleaning + 500 transport = 2,000 -> 30% = 600
        assert job["total_cents"] == 200_000
        assert job["deposit_required_cents"] == 60_000

    def test_a_deposit_on_the_cleaning_alone_would_under_cover_the_trip(self, client):
        """The bug this fixes, stated as a test: without transport in the total
        the deposit is short by 30% of the fee -- money Mercy has already spent
        on fuel by the time a client cancels."""
        set_fee(client, "ruiru", 500)
        with_t = client.post("/api/admin/quotes", headers=HDR,
                             json={**BASE, "items": SOFA}).json()["job"]
        set_fee(client, "ruiru", 0)
        without = client.post("/api/admin/quotes", headers=HDR,
                              json={**BASE, "items": SOFA}).json()["job"]
        short = with_t["deposit_required_cents"] - without["deposit_required_cents"]
        assert short == 15_000, "30% of the KSh 500 trip"

    def test_paying_the_deposit_still_unlocks_booking(self, client):
        """The gate must read the new total, not a stale one."""
        set_fee(client, "ruiru", 500)
        ref = client.post("/api/admin/quotes", headers=HDR,
                          json={**BASE, "items": SOFA}).json()["quote_ref"]
        client.post(f"/api/admin/jobs/{ref}/payments", headers=HDR,
                    json={"amount_cents": 60_000, "kind": "deposit"})
        r = client.post(f"/api/admin/jobs/{ref}/book", headers=HDR,
                        json={"scheduled_at": "2026-09-01", "window": "morning"}).json()
        assert r["ok"] is True, r

    def test_a_deposit_short_by_the_transport_share_is_refused(self, client):
        set_fee(client, "ruiru", 500)
        ref = client.post("/api/admin/quotes", headers=HDR,
                          json={**BASE, "items": SOFA}).json()["quote_ref"]
        client.post(f"/api/admin/jobs/{ref}/payments", headers=HDR,
                    json={"amount_cents": 45_000, "kind": "deposit"})   # 30% of cleaning only
        r = client.post(f"/api/admin/jobs/{ref}/book", headers=HDR,
                        json={"scheduled_at": "2026-09-01", "window": "morning"}).json()
        assert r["ok"] is False
        assert "short" in r["reason"].lower()


class TestOperatorOverride:
    def test_mercy_can_override_the_trip_on_one_job(self, client):
        set_fee(client, "ruiru", 400)
        ref = client.post("/api/admin/quotes", headers=HDR,
                          json={**BASE, "items": SOFA}).json()["quote_ref"]
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": SOFA, "addons": [], "reason": "already passing that way",
            "operator": {"transport_override": 0},
        }).json()
        assert r["new_total_cents"] == 150_000       # the fee is gone

    def test_the_override_names_itself_in_the_log(self, client):
        set_fee(client, "ruiru", 400)
        ref = client.post("/api/admin/quotes", headers=HDR,
                          json={**BASE, "items": SOFA}).json()["quote_ref"]
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": SOFA, "addons": [], "reason": "three streets past the edge",
            "operator": {"transport_override": 650},
        })
        detail = client.get(f"/api/admin/jobs/{ref}/changes",
                            headers=HDR).json()["changes"][-1]["detail"]
        assert "transport" in detail.lower() and "650" in detail

    def test_without_an_override_a_reprice_keeps_the_zone_fee(self, client):
        """A re-price must never silently drop the travel Mercy is owed."""
        set_fee(client, "ruiru", 400)
        ref = client.post("/api/admin/quotes", headers=HDR,
                          json={**BASE, "items": SOFA}).json()["quote_ref"]
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                        json={"items": SOFA, "addons": [], "reason": "no change"}).json()
        assert r["new_total_cents"] == 190_000       # 1,500 + 400

    def test_a_customer_cannot_set_their_own_transport(self, client):
        set_fee(client, "ruiru", 400)
        sneaky = client.post("/api/quote", json={
            **BASE, "items": SOFA, "operator": {"transport_override": 0},
        }).json()
        assert sneaky["transport"] == 400
