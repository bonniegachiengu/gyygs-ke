"""The board is on a public URL behind one shared PIN.

Without throttling, "one shared PIN" means "as many guesses as you like" against
a surface holding customer names, phone numbers and payment records. These tests
pin the behaviour that makes the PIN worth having.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.repositories.base import Lead
from app.repositories.sqlite import SqliteLeadRepository
from app.main import create_app

PIN = "test-pin-9999"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "leads.db")
    # The board route reads the repository, so a real row has to exist for the
    # ACCEPTED-pin cases below to exercise anything past the guard. Same shape
    # the self-serve lane writes, as in test_admin_routes.py.
    SqliteLeadRepository(db).append(
        Lead(
            ref="MY-260824-001", timestamp=datetime.now(timezone.utc),
            name="Faith", phone="254722000001",
            items="Sofa 3 seats", subtotal=1500, discount=0, total=1500,
            area="ruiru", preferred="2026-09-01 morning",
            visit_first=False, sent_to_wa=True,
        )
    )
    monkeypatch.setenv("ADMIN_PIN", PIN)
    monkeypatch.setenv("LEAD_DB_PATH", db)
    monkeypatch.setenv("LEAD_STORE", "sqlite")
    get_settings.cache_clear()
    # conftest's autouse _fresh_pin_limiter gives this test its own budget.
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def wrong(client, ip="203.0.113.7"):
    return client.get("/api/admin/board",
                      headers={"X-Admin-PIN": "nope", "CF-Connecting-IP": ip})


class TestThrottle:
    def test_a_few_wrong_guesses_are_plain_401s(self, client):
        for _ in range(5):
            assert wrong(client).status_code == 401

    def test_guessing_past_the_limit_is_refused_with_429(self, client):
        for _ in range(5):
            wrong(client)
        r = wrong(client)
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    def test_the_correct_pin_still_works_while_throttled(self, client):
        """The throttle makes guessing impractical. It must not lock out the one
        person who is supposed to get in -- Mercy mistyping twice on a phone is
        the common case, not an attack."""
        for _ in range(8):
            wrong(client)
        r = client.get("/api/admin/board",
                       headers={"X-Admin-PIN": PIN, "CF-Connecting-IP": "203.0.113.7"})
        assert r.status_code == 200

    def test_one_ip_cannot_lock_out_another(self, client):
        for _ in range(8):
            wrong(client, ip="198.51.100.1")
        assert wrong(client, ip="203.0.113.9").status_code == 401

    def test_success_never_consumes_the_budget(self, client):
        for _ in range(10):
            client.get("/api/admin/board",
                       headers={"X-Admin-PIN": PIN, "CF-Connecting-IP": "203.0.113.7"})
        # A wrong guess afterwards is still only the FIRST failure.
        assert wrong(client).status_code == 401


class TestUnchangedBehaviour:
    def test_no_pin_configured_is_still_503(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_PIN", "")
        get_settings.cache_clear()
        r = client.get("/api/admin/board", headers={"X-Admin-PIN": "anything"})
        assert r.status_code == 503

    def test_a_missing_header_is_refused(self, client):
        assert client.get("/api/admin/board").status_code == 401
