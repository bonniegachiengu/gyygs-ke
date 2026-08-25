"""The operator quote must be a strict SUPERSET of the customer calculator.

WHY THIS FILE EXISTS. The first operator composer was written from the
catalogue's shape rather than from the customer calculator's code, and came out
NARROWER than what any customer can do unaided: one line per service, `qty`
pinned to 1, and no chair extras, house tiers, extra bedrooms, modifiers or
add-ons at all. Mercy could not quote two sofas, or sheers AND heavy curtains.
It priced correctly -- it just could not express most baskets.

Reviewer discipline is what failed there, so this is checked mechanically:

  1. every degree of freedom the CATALOGUE grants must be expressible through
     the operator lane, and price identically to the customer lane;
  2. the operator board's own source must render a control for each of them,
     so a future edit cannot quietly drop one back to a subset.

(2) is a source scan rather than a DOM test because the board is a single
static HTML file with no JS test harness. It is coarse, and it is still the
thing that would have caught the original bug.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_quote_limiter
from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter
from app.main import create_app

PIN = "test-pin-9999"
HDR = {"X-Admin-PIN": PIN}
BOARD = Path(__file__).resolve().parents[3] / "apps" / "admin" / "index.html"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PIN", PIN)
    monkeypatch.setenv("LEAD_DB_PATH", str(tmp_path / "leads.db"))
    monkeypatch.setenv("LEAD_STORE", "sqlite")
    monkeypatch.setenv("DEPOSIT_PCT", "30")
    get_settings.cache_clear()
    app = create_app()
    # This module deliberately fires many quotes to compare prices pair by pair,
    # and every TestClient request arrives from the same host -- so the customer
    # quote limiter throttles it and the failures look like pricing bugs. A
    # generous fresh limiter keeps this file testing what it claims to test.
    app.dependency_overrides[get_quote_limiter] = lambda: SlidingWindowLimiter(10_000, 10_000)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def catalogue(client):
    return client.get("/api/pricing").json()


# A basket that exercises EVERY freedom at once: two lines of one service,
# per-seat counts, chair extras, three curtain sizes, a carpet modifier, a
# house tier with extra bedrooms, and both add-on shapes.
def maximal_basket():
    return {
        "items": [
            {"service": "sofa", "seats": 3,
             "extras": [{"key": "dining_chair", "qty": 4},
                        {"key": "office_chair", "qty": 1}]},
            {"service": "sofa", "seats": 2},                      # a SECOND sofa
            {"service": "carpet", "size": "5x7", "qty": 2,
             "modifiers": ["thick_shaggy"]},
            {"service": "curtains", "size": "sheers", "qty": 4},
            {"service": "curtains", "size": "large", "qty": 2},    # a second size
            {"service": "mattress", "size": "5x6", "qty": 1},
            {"service": "house", "tier": "4br", "extra_bedrooms": 2},
        ],
        "addons": [{"key": "bathroom", "qty": 3},
                   {"key": "fridge", "qty": 1}],
        "area": "nairobi",
        "preferred": {"day": "2026-09-01", "window": "morning"},
        "contact": {"name": "Parity"},
        "recurring": False,
    }


class TestBothLanesPriceEveryFreedomIdentically:
    def test_the_maximal_basket_prices_the_same_on_both_lanes(self, client):
        basket = maximal_basket()
        customer = client.post("/api/quote", json=basket).json()
        operator = client.post("/api/admin/quotes", headers=HDR, json=basket).json()
        assert operator["total"] == customer["total"]
        assert operator["total"] > 0

    def test_the_maximal_basket_is_actually_accepted(self, client):
        r = client.post("/api/admin/quotes", headers=HDR, json=maximal_basket())
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    # Each pair is a VALID basket either side, differing in exactly one freedom.
    # Stripping a field from a whole basket instead produced invalid baskets
    # (extra_bedrooms only apply beyond the last house tier, and the engine
    # rightly refuses otherwise) -- which proved nothing about pricing.
    FREEDOM_PAIRS = {
        "seats":          ({"service": "sofa", "seats": 2},
                           {"service": "sofa", "seats": 5}),
        "extras":         ({"service": "sofa", "seats": 2},
                           {"service": "sofa", "seats": 2,
                            "extras": [{"key": "dining_chair", "qty": 4}]}),
        "size":           ({"service": "carpet", "size": "3x5"},
                           {"service": "carpet", "size": "8x10"}),
        "qty":            ({"service": "carpet", "size": "5x7", "qty": 1},
                           {"service": "carpet", "size": "5x7", "qty": 3}),
        "modifiers":      ({"service": "carpet", "size": "5x7"},
                           {"service": "carpet", "size": "5x7",
                            "modifiers": ["thick_shaggy"]}),
        "tier":           ({"service": "house", "tier": "studio"},
                           {"service": "house", "tier": "3br"}),
        "extra_bedrooms": ({"service": "house", "tier": "4br"},
                           {"service": "house", "tier": "4br", "extra_bedrooms": 3}),
    }

    @pytest.mark.parametrize("freedom", sorted(FREEDOM_PAIRS))
    def test_each_freedom_actually_moves_the_price(self, client, freedom):
        """Proof the field is not merely ACCEPTED and ignored.

        A field the engine silently drops would let the operator surface look
        complete while quoting the wrong number -- worse than refusing.
        """
        lo, hi = self.FREEDOM_PAIRS[freedom]
        base = {k: v for k, v in maximal_basket().items() if k not in ("items", "addons")}
        a = client.post("/api/quote", json={**base, "items": [lo], "addons": []})
        b = client.post("/api/quote", json={**base, "items": [hi], "addons": []})
        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text
        assert a.json()["total"] != b.json()["total"], (
            f"{freedom!r} did not change the price — is it actually wired?")

    def test_add_ons_move_the_price_too(self, client):
        base = {k: v for k, v in maximal_basket().items() if k not in ("items", "addons")}
        items = [{"service": "sofa", "seats": 2}]
        a = client.post("/api/quote", json={**base, "items": items, "addons": []}).json()
        b = client.post("/api/quote", json={**base, "items": items,
                                            "addons": [{"key": "bathroom", "qty": 3}]}).json()
        assert b["total"] > a["total"]

    def test_a_second_line_of_the_same_service_is_not_collapsed(self, client):
        """Two sofas must cost more than one. The old composer could not even
        express this, so nothing proved the engine handled it."""
        one = {**maximal_basket(), "items": [{"service": "sofa", "seats": 3}]}
        two = {**maximal_basket(), "items": [{"service": "sofa", "seats": 3},
                                             {"service": "sofa", "seats": 2}]}
        assert (client.post("/api/quote", json=two).json()["total"]
                > client.post("/api/quote", json=one).json()["total"])

    def test_two_sizes_of_the_same_service_both_count(self, client):
        """Sheers AND heavy curtains — Bonnie's own example."""
        one = {**maximal_basket(),
               "items": [{"service": "curtains", "size": "sheers", "qty": 4}]}
        two = {**maximal_basket(),
               "items": [{"service": "curtains", "size": "sheers", "qty": 4},
                         {"service": "curtains", "size": "large", "qty": 2}]}
        assert (client.post("/api/quote", json=two).json()["total"]
                > client.post("/api/quote", json=one).json()["total"])


class TestTheBoardRendersEveryFreedom:
    """A source scan of the operator board.

    Coarse on purpose: it asserts the CONTROL EXISTS, not that it looks right.
    That is enough to catch a surface silently narrowing again, which is the
    failure this file was written for.
    """

    @pytest.fixture(autouse=True)
    def board(self):
        assert BOARD.exists(), f"operator board not found at {BOARD}"
        self.src = BOARD.read_text(encoding="utf-8")

    @pytest.mark.parametrize("field", [
        "seats",            # per_unit count
        "qty",              # how many of a size
        "tier",             # house
        "extra_bedrooms",   # house, beyond the last tier
        "size",             # size_tier
        "modifiers",        # per-item modifier chips
        "extras",           # dining / office chairs
    ])
    def test_the_composer_handles(self, field):
        assert field in self.src, f"the board never mentions {field!r}"

    def test_it_can_add_another_line_of_the_same_service(self):
        assert "Add another" in self.src
        assert "addLine" in self.src

    def test_it_can_remove_a_line(self):
        assert "data-rm" in self.src

    def test_add_ons_are_offered(self):
        assert "readAddons" in self.src
        assert "addonsHTML" in self.src

    def test_visit_triggering_options_are_shown(self):
        """`larger` and `above` push a job to visit-first pricing; hiding them
        would silently quote a firm price for a job that needs a look."""
        assert "larger" in self.src
        assert "above" in self.src

    def test_addons_are_actually_sent_not_hardcoded_empty(self):
        """The original bug in miniature: `addons:[]` was posted literally, so
        every add-on the operator picked was discarded on the way out."""
        assert "addons:[]" not in self.src.replace(" ", "")

    def test_the_reduced_composer_is_gone(self):
        for dead in ("chipRows", "readChips", "wireChips"):
            assert dead not in self.src, f"{dead} survived — two composers now exist"


class TestNoSecondPricingPath:
    def test_the_board_never_computes_a_total_itself(self):
        """Every price on the operator surface must come from the engine.
        A total computed in the browser is a second source of truth."""
        src = BOARD.read_text(encoding="utf-8")
        for banned in ("subtotal =", "total +=", "computeTotal", "sumItems"):
            assert banned not in src, f"the board looks like it prices locally: {banned!r}"
