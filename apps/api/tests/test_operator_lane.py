"""The operator lane — Mercy quoting from a chat.

The assertion that matters: the operator lane and the calculator lane produce
the SAME price for the same basket, because they share one pricing engine. If
they could diverge, the board and the customer would disagree about what a job
costs -- which is the failure MYRAH_WHATSAPP_AND_CMS.md §3d's "one source of
truth" exists to prevent.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

PIN = "test-pin-9999"
HDR = {"X-Admin-PIN": PIN}

# The CLAUDE.md worked example: 3-seat sofa 1,500 + mattress 5x6 1,500 + fridge 800.
BASKET = {
    "items": [{"service": "sofa", "seats": 3}, {"service": "mattress", "size": "5x6", "qty": 1}],
    "addons": [{"key": "fridge"}],
    "area": "ruiru",
    "preferred": {"day": "2026-09-01", "window": "morning"},
    "contact": {"name": "Chat Customer"},
    "recurring": False,
}


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


class TestOneSourceOfTruth:
    def test_both_lanes_price_the_same_basket_identically(self, client):
        """★ The reason the operator lane calls create_quote and prices nothing."""
        customer = client.post("/api/quote", json=BASKET).json()
        mercy = client.post("/api/admin/quotes", headers=HDR, json=BASKET).json()
        assert mercy["total"] == customer["total"] == 3800
        assert mercy["ok"] is True

    def test_the_operator_uses_the_same_catalogue_chips(self, client):
        pub = client.get("/api/pricing").json()
        ops = client.get("/api/admin/catalogue", headers=HDR).json()
        assert [s["key"] for s in ops["services"]] == [s["key"] for s in pub["services"]]

    def test_the_catalogue_needs_the_pin(self, client):
        assert client.get("/api/admin/catalogue").status_code == 401


class TestOperatorQuoteLandsOnTheBoard:
    def test_it_appears_under_quoted_marked_operator(self, client):
        ref = client.post("/api/admin/quotes", headers=HDR, json=BASKET).json()["quote_ref"]
        quoted = client.get("/api/admin/board", headers=HDR).json()["columns"]["quoted"]
        job = next(j for j in quoted if j["ref"] == ref)
        assert job["source"] == "operator", "provenance must distinguish the two lanes"
        assert job["client_name"] == "Chat Customer"

    def test_the_two_lanes_are_distinguishable_on_the_board(self, client):
        client.post("/api/quote", json=BASKET)
        client.post("/api/admin/quotes", headers=HDR, json=BASKET)
        sources = sorted(j["source"] for j in
                         client.get("/api/admin/board", headers=HDR).json()["columns"]["quoted"])
        assert sources == ["calculator", "operator"]

    def test_no_duplicate_record_is_created(self, client):
        """create_quote writes ONE lead; the operator lane re-reads it, not re-writes."""
        client.post("/api/admin/quotes", headers=HDR, json=BASKET)
        assert len(client.get("/api/admin/board", headers=HDR).json()["columns"]["quoted"]) == 1

    def test_the_response_carries_a_sendable_whatsapp_url(self, client):
        """Mercy is mid-chat; she must be able to send the price without a second call."""
        r = client.post("/api/admin/quotes", headers=HDR, json=BASKET).json()
        assert r["whatsapp_url"].startswith("https://wa.me/")
        assert "Myrah" in __import__("urllib.parse", fromlist=["unquote"]).unquote(r["whatsapp_url"])

    def test_the_deposit_gate_applies_to_operator_quotes_too(self, client):
        ref = client.post("/api/admin/quotes", headers=HDR, json=BASKET).json()["quote_ref"]
        r = client.post(f"/api/admin/jobs/{ref}/book", headers=HDR,
                        json={"scheduled_at": "2026-09-01"}).json()
        assert r["ok"] is False
        assert "KSh 1,140" in r["reason"], "same 30% gate, whichever lane created it"

    def test_a_quote_needing_a_visit_carries_no_deposit(self, client):
        r = client.post("/api/admin/quotes", headers=HDR, json={
            **BASKET, "items": [{"service": "post_construction"}],
        }).json()
        assert r["job"]["visit_first"] is True
        assert r["job"]["deposit_required_cents"] == 0

    def test_operator_quotes_need_the_pin(self, client):
        assert client.post("/api/admin/quotes", json=BASKET).status_code == 401


class TestGeneratedCopyReadsMyrah:
    """Customer-facing. The message a client receives must carry the brand."""

    def test_the_wa_text_greets_as_myrah(self, client):
        from urllib.parse import unquote
        t = unquote(client.post("/api/quote", json=BASKET).json()["whatsapp_url"].split("?text=", 1)[1])
        assert "Myrah Cleaning" in t
        import re
        assert not re.search(r"Myra(?!h)", t), "no bare 'Myra' may reach a customer"

    def test_the_operator_lane_message_reads_myrah_too(self, client):
        from urllib.parse import unquote
        import re
        t = unquote(client.post("/api/admin/quotes", headers=HDR, json=BASKET)
                    .json()["whatsapp_url"].split("?text=", 1)[1])
        assert "Myrah Cleaning" in t
        assert not re.search(r"Myra(?!h)", t)
