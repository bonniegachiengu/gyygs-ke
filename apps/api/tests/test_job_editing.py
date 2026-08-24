"""Editable jobs — MYRAH_OPERATIONS_DESIGN.md §3b.

Plus a regression for the bug Bonnie hit on the staging board: selecting a
size-tier service (curtains) alongside a per-unit one (sofa) failed to price,
because the operator UI sent `seats`/`qty` for every service regardless of its
pricing strategy.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
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
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def new_job(client, items=None, name="Njeri"):
    r = client.post("/api/admin/quotes", headers=HDR, json={
        "items": items or [{"service": "sofa", "seats": 3}],
        "addons": [], "area": "nairobi",
        "preferred": {"day": "2026-09-01", "window": "morning"},
        "contact": {"name": name}, "recurring": False,
    })
    assert r.status_code == 200, r.text
    return r.json()["quote_ref"]


# ── the bug Bonnie hit ──────────────────────────────────────────────────────

class TestMixedPricingStrategies:
    """★ Sofa (per_unit) + Curtains (size_tier) in one basket.

    The board used to send {seats, qty} for BOTH, so the engine correctly
    refused with "choose a size for curtains" -- and the UI showed a generic
    "Could not price that", hiding the one sentence that explained it.
    """

    def test_a_size_tier_service_prices_when_given_a_size(self, client):
        ref = new_job(client, [
            {"service": "sofa", "seats": 2},
            {"service": "curtains", "size": "standard", "qty": 1},
        ])
        job = client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()
        assert job["total_cents"] > 0

    def test_a_size_tier_service_WITHOUT_a_size_is_refused_legibly(self, client):
        """The engine's sentence must survive to the caller, not be swallowed."""
        r = client.post("/api/admin/quotes", headers=HDR, json={
            "items": [{"service": "curtains", "seats": 1, "qty": 1}],
            "addons": [], "area": "nairobi",
            "preferred": {"day": "2026-09-01", "window": "morning"},
            "contact": {"name": "X"}, "recurring": False,
        })
        assert r.status_code == 400
        assert "size" in r.json()["detail"].lower()
        assert "curtains" in r.json()["detail"].lower()

    def test_both_lanes_price_a_mixed_basket_identically(self, client):
        basket = {
            "items": [{"service": "sofa", "seats": 2},
                      {"service": "curtains", "size": "standard", "qty": 1}],
            "addons": [], "area": "nairobi",
            "preferred": {"day": "2026-09-01", "window": "morning"},
            "contact": {"name": "Same Basket"}, "recurring": False,
        }
        customer = client.post("/api/quote", json=basket).json()
        mercy = client.post("/api/admin/quotes", headers=HDR, json=basket).json()
        assert mercy["total"] == customer["total"]


# ── §3b: editing ────────────────────────────────────────────────────────────

class TestRepricing:
    def test_adding_a_service_raises_the_total_via_the_engine(self, client):
        ref = new_job(client)                       # sofa 3 seats = 1,500
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3},
                      {"service": "curtains", "size": "standard", "qty": 1}],
            "reason": "after site visit",
        }).json()
        assert r["ok"] is True
        assert r["new_total_cents"] > r["old_total_cents"]

    def test_removing_a_service_lowers_it(self, client):
        ref = new_job(client, [{"service": "sofa", "seats": 3},
                               {"service": "curtains", "size": "standard", "qty": 1}])
        before = client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()["total_cents"]
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "reason": "client dropped curtains",
        }).json()
        assert r["new_total_cents"] < before

    def test_there_is_no_endpoint_that_accepts_a_total(self, client):
        """Server-authoritative: a hand-typed figure must be impossible."""
        ref = new_job(client)
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
            "items": [{"service": "sofa", "seats": 3}], "total": 999_999,
        }).json()
        assert r["new_total_cents"] == 150_000, "the engine priced it, not the caller"

    def test_an_invalid_basket_is_refused_and_the_job_is_untouched(self, client):
        ref = new_job(client)
        before = client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()["total_cents"]
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                        json={"items": [{"service": "curtains", "qty": 1}]})
        assert r.status_code == 400
        assert client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()["total_cents"] == before


class TestChangeRecord:
    def test_every_reprice_appends_a_record(self, client):
        ref = new_job(client)
        for n in (2, 4):
            client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR, json={
                "items": [{"service": "sofa", "seats": n}], "reason": f"changed to {n}"})
        ch = client.get(f"/api/admin/jobs/{ref}/changes", headers=HDR).json()["changes"]
        assert len(ch) == 2
        assert [c["detail"] for c in ch] == ["changed to 2", "changed to 4"]

    def test_the_record_carries_the_old_and_new_totals(self, client):
        ref = new_job(client)                       # 1,500
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                    json={"items": [{"service": "sofa", "seats": 6}]})
        c = client.get(f"/api/admin/jobs/{ref}/changes", headers=HDR).json()["changes"][0]
        assert c["old_total_cents"] == 150_000
        assert c["new_total_cents"] > c["old_total_cents"]

    def test_history_is_append_only(self, client):
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                    json={"items": [{"service": "sofa", "seats": 4}]})
        first = client.get(f"/api/admin/jobs/{ref}/changes", headers=HDR).json()["changes"][0]
        client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                    json={"items": [{"service": "sofa", "seats": 5}]})
        ch = client.get(f"/api/admin/jobs/{ref}/changes", headers=HDR).json()["changes"]
        assert ch[0] == first, "the earlier record must survive unchanged"


class TestNotes:
    def test_instructions_round_trip(self, client):
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/notes", headers=HDR,
                    json={"notes": "Gate code 4417. Dog is friendly. Start upstairs."})
        job = client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()
        assert "Gate code 4417" in job["notes"]

    def test_saving_notes_is_recorded_as_a_change(self, client):
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/notes", headers=HDR, json={"notes": "Ring twice"})
        ch = client.get(f"/api/admin/jobs/{ref}/changes", headers=HDR).json()["changes"]
        assert ch[-1]["kind"] == "notes"

    def test_notes_do_not_change_the_price(self, client):
        ref = new_job(client)
        before = client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()["total_cents"]
        client.post(f"/api/admin/jobs/{ref}/notes", headers=HDR, json={"notes": "anything"})
        assert client.get(f"/api/admin/jobs/{ref}", headers=HDR).json()["total_cents"] == before


class TestDepositInteraction:
    """§3b: a deposit already paid is never clawed back."""

    def test_a_paid_deposit_survives_a_reprice(self, client):
        ref = new_job(client)                                   # 1,500 -> 450 deposit
        client.post(f"/api/admin/jobs/{ref}/payments", headers=HDR,
                    json={"amount_cents": 45_000, "kind": "deposit"})
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                        json={"items": [{"service": "sofa", "seats": 6}]}).json()
        assert r["deposit_already_paid_cents"] == 45_000
        assert r["job"]["deposit_paid_cents"] == 45_000

    def test_a_booked_job_stays_booked_when_scope_grows(self, client):
        """Growing the job must not un-book a slot the client already secured."""
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/payments", headers=HDR,
                    json={"amount_cents": 45_000, "kind": "deposit"})
        client.post(f"/api/admin/jobs/{ref}/book", headers=HDR,
                    json={"scheduled_at": "2026-09-01", "window": "morning"})
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                        json={"items": [{"service": "sofa", "seats": 8}],
                              "reason": "added on the morning"}).json()
        assert r["job"]["status"] == "booked"

    def test_the_extra_shows_as_owing(self, client):
        ref = new_job(client)
        client.post(f"/api/admin/jobs/{ref}/payments", headers=HDR,
                    json={"amount_cents": 45_000, "kind": "deposit"})
        r = client.post(f"/api/admin/jobs/{ref}/reprice", headers=HDR,
                        json={"items": [{"service": "sofa", "seats": 6}]}).json()
        assert r["job"]["balance_cents"] == r["new_total_cents"] - 45_000


class TestAuth:
    def test_editing_needs_the_pin(self, client):
        ref = new_job(client)
        assert client.post(f"/api/admin/jobs/{ref}/reprice",
                           json={"items": [{"service": "sofa", "seats": 1}]}).status_code == 401
        assert client.post(f"/api/admin/jobs/{ref}/notes", json={"notes": "x"}).status_code == 401
