"""Drift guard between the repo-root `.env.example` and `Settings`.

`Settings` uses `extra="ignore"`, so a stray key in `.env.example` would never raise on
its own — which is exactly how a documented-but-unread setting ships. These tests make
that drift a test failure instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from tests.conftest import REPO_ROOT

ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Keys that live in .env.example for other services, not for the API process.
NON_API_KEYS = {"CLOUDFLARE_TUNNEL_TOKEN", "DATABASE_URL"}


def _env_example_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file(), f"missing {ENV_EXAMPLE}"


def test_every_env_example_key_is_a_settings_field() -> None:
    known = {f.upper() for f in Settings.model_fields}
    unknown = _env_example_keys(ENV_EXAMPLE) - known - NON_API_KEYS
    assert not unknown, f".env.example documents keys Settings does not read: {sorted(unknown)}"


def test_settings_constructs_from_env_example() -> None:
    s = Settings(_env_file=ENV_EXAMPLE)

    assert s.whatsapp_number == "254716869648"
    assert s.public_site_host == "myra.vyybandasky.online"
    assert s.lead_store == "memory"

    # python-dotenv strips the trailing `# manual | oscu` comment from an unquoted value.
    assert s.etims_mode == "manual"
    assert s.etims_enabled is False
    assert s.vat_registered is False
    assert s.business_kra_pin == "pending"

    # Pricing rules — both are pending Mercy's confirmation, see CLAUDE.md.
    assert s.minimum_callout == 0
    assert s.recurring_discount_pct == 10
    assert s.recurring_requires_visit is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://myra.vyybandasky.online", ["https://myra.vyybandasky.online"]),
        ("https://a.example, http://b.example", ["https://a.example", "http://b.example"]),
        ("", []),
    ],
)
def test_cors_origins_splits_on_comma(raw: str, expected: list[str]) -> None:
    # Declared as `str` on purpose: pydantic-settings JSON-parses complex-typed env
    # vars, so `list[str]` would raise SettingsError on a plain comma-separated value.
    assert Settings(_env_file=None, cors_origins=raw).cors_origin_list == expected
