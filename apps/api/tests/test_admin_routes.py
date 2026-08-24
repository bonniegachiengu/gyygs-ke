"""Mercy's operator surface, over HTTP.

The important assertion in this file is that the deposit gate holds THROUGH THE
ROUTE. The gate lives in the domain service precisely so no lane can bypass it;
this proves the admin lane doesn't.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.repositories.base import Lead
from app.repositories.sqlite import SqliteLeadRepository

PIN = "test-pin-9999"
HDR = {"X-Admin-PIN": PIN}


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "leads.db")
    # A calculator quote, exactly as the self-serve lane writes one.
    SqliteLeadRepository(db).append(
        Lead(
            ref="MY-260824-001", timestamp=datetime.now(timezone.utc),
            name="Faith", phone="254722000001",
            items="Sofa 3 seats; Mattress 5x6; Fridge",
            # whole shillings, exactly as the pricing engine writes them:
            # KSh 3,800 -- the CLAUDE.md worked example.
            subtotal=3800, discount=0, total=3800,
            area="ruiru", preferred="2026-09-01 morning",
            visit_first=False, sent_to_wa=True,
        )
    )
    monkeypatch.setenv("ADMIN_PIN", PIN)
    monkeypatch.setenv("LEAD_DB_PATH", db)
    monkeypatch.setenv("LEAD_STORE", "sqlite")
    monkeypatch.setenv("DEPOSIT_PCT", "30")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


class TestAuth:
    def test_no_pin_is_rejected(self, client):
        assert client.get("/api/admin/board").status_code == 401

    def test_wrong_pin_is_rejected(self, client):
        assert client.get("/api/admin/board", headers={"X-Admin-PIN": "nope"}).status_code == 401

    def test_correct_pin_gets_the_board(self, client):
        assert client.get("/api/admin/board", headers=HDR).status_code == 200


class TestSelfServeLaneLandsOnTheBoard:
    """The lane that previously 'hit WhatsApp and died'."""

    def test_a_calculator_quote_appears_as_a_quoted_job(self, client):
        b = client.get("/api/admin/board", headers=HDR).json()
        quoted = b["columns"]["quoted"]
        assert len(quoted) == 1
        assert quoted[0]["ref"] == "MY-260824-001"
        assert quoted[0]["source"] == "calculator"

    def test_a_NEW_calculator_quote_lands_on_the_board_too(self, client):
        """End to end: POST /api/quote -> visible to Mercy, no extra wiring."""
        r = client.post("/api/quote", json={
            "items": [{"service": "sofa", "seats": 2}],
            "addons": [], "area": "ruiru",
            "preferred": {"day": "2026-09-05", "window": "afternoon"},
            "contact": {"name": "Walk-in Wanjiru"}, "recurring": False,
        })
        assert r.status_code == 200
        ref = r.json()["quote_ref"]
        refs = [j["ref"] for j in client.get("/api/admin/board", headers=HDR).json()["columns"]["quoted"]]
        assert ref in refs, "a quote the customer just built must be on Mercy's board"

    def test_the_board_carries_what_the_deposit_needs_to_be(self, client):
        job = client.get("/api/admin/board", headers=HDR).json()["columns"]["quoted"][0]
        assert job["deposit_required_cents"] == 114_000     # 30% of 3,800
        assert job["deposit_satisfied"] is False


class TestDepositGateThroughTheRoute:
    """★ The gate must hold on the wire, not just in the domain."""

    def test_booking_without_a_deposit_is_refused_with_a_readable_reason(self, client):
        r = client.post("/api/admin/jobs/MY-260824-001/book", headers=HDR,
                        json={"scheduled_at": "2026-09-01", "window": "morning"})
        assert r.status_code == 200, "a refusal is an outcome Mercy reads, not an error page"
        body = r.json()
        assert body["ok"] is False
        assert "KSh 1,140" in body["reason"]
        assert body["job"]["status"] == "quoted", "the job must not have moved"

    def test_a_partial_deposit_is_still_refused(self, client):
        client.post("/api/admin/jobs/MY-260824-001/payments", headers=HDR,
                    json={"amount_cents": 50_000, "kind": "deposit"})
        r = client.post("/api/admin/jobs/MY-260824-001/book", headers=HDR,
                        json={"scheduled_at": "2026-09-01"})
        assert r.json()["ok"] is False
        assert "short" in r.json()["reason"]

    def test_a_full_deposit_books_it(self, client):
        client.post("/api/admin/jobs/MY-260824-001/payments", headers=HDR,
                    json={"amount_cents": 114_000, "kind": "deposit", "mpesa_ref": "TFE5G7H8L3"})
        r = client.post("/api/admin/jobs/MY-260824-001/book", headers=HDR,
                        json={"scheduled_at": "2026-09-01", "window": "morning"})
        assert r.json()["ok"] is True
        assert r.json()["job"]["status"] == "booked"
        assert r.json()["job"]["scheduled_at"] == "2026-09-01 morning"

    def test_a_duplicate_mpesa_ref_is_refused_on_the_wire(self, client):
        p = {"amount_cents": 50_000, "kind": "deposit", "mpesa_ref": "DUP999"}
        assert client.post("/api/admin/jobs/MY-260824-001/payments", headers=HDR, json=p).json()["ok"]
        r = client.post("/api/admin/jobs/MY-260824-001/payments", headers=HDR, json=p)
        assert r.json()["ok"] is False
        assert "DUP999" in r.json()["reason"]


class TestTheFullDayMercyActuallyHas:
    def _pay_and_book(self, client):
        client.post("/api/admin/jobs/MY-260824-001/payments", headers=HDR,
                    json={"amount_cents": 114_000, "kind": "deposit"})
        client.post("/api/admin/jobs/MY-260824-001/book", headers=HDR,
                    json={"scheduled_at": "2026-09-01", "window": "morning"})

    def test_quote_to_paid_end_to_end(self, client):
        self._pay_and_book(client)
        client.post("/api/admin/jobs/MY-260824-001/complete", headers=HDR)

        board = client.get("/api/admin/board", headers=HDR).json()
        assert [j["ref"] for j in board["columns"]["unpaid"]] == ["MY-260824-001"], \
            "completed but not settled belongs under Unpaid"

        client.post("/api/admin/jobs/MY-260824-001/payments", headers=HDR,
                    json={"amount_cents": 266_000, "kind": "balance"})
        job = client.get("/api/admin/jobs/MY-260824-001", headers=HDR).json()
        assert job["status"] == "paid"
        assert job["balance_cents"] == 0

    def test_a_receipt_is_issuable_and_names_myrah(self, client):
        self._pay_and_book(client)
        r = client.get("/api/admin/jobs/MY-260824-001/receipt", headers=HDR).json()
        assert r["business"]["name"] == "Myrah Cleaning Services"
        assert r["job_ref"] == "MY-260824-001"
        assert r["paid_cents"] == 114_000

    def test_etims_stays_stubbed_until_registration(self, client):
        r = client.get("/api/admin/jobs/MY-260824-001/receipt", headers=HDR).json()
        assert r["business"]["etims"] == "pending registration"

    def test_the_client_profile_shows_history_and_lifetime_value(self, client):
        self._pay_and_book(client)
        cid = client.get("/api/admin/jobs/MY-260824-001", headers=HDR).json()["client_id"]
        prof = client.get(f"/api/admin/clients/{cid}", headers=HDR).json()
        assert prof["client"]["name"] == "Faith"
        assert prof["job_count"] == 1
        assert prof["lifetime_cents"] == 114_000

    def test_an_unknown_job_is_a_clean_404(self, client):
        assert client.get("/api/admin/jobs/NOPE", headers=HDR).status_code == 404
