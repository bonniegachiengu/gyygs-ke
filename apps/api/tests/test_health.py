"""ARCHITECTURE.md §5: `GET /api/health` -> `{"status": "ok", "version": "<semver>"}`."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings


def test_health_returns_ok_and_version(client: TestClient, settings: Settings) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": settings.app_version}


def test_health_is_mounted_under_api_prefix(client: TestClient) -> None:
    # The whole app lives under /api so nginx can proxy a single prefix and the
    # frontend can call it same-origin. A bare /health would break that contract.
    assert client.get("/health").status_code == 404


def test_openapi_is_served_for_client_generation(client: TestClient) -> None:
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    assert "/api/health" in r.json()["paths"]
