"""Application settings, read from the environment / .env.

Every key here is documented in the repo-root `.env.example`. `tests/test_settings.py`
loads that file and asserts this model can construct from it, so adding a key to one
without the other fails the suite.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──
    app_version: str = "0.1.0"
    # NOTE: this is deliberately `str`, not `list[str]`. pydantic-settings JSON-parses
    # complex-typed env vars, and `CORS_ORIGINS=https://myra.vyybandasky.online` is not
    # valid JSON — declaring it as a list raises SettingsError at import time.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    public_site_host: str = "myra.vyybandasky.online"

    # ── WhatsApp handoff ──
    whatsapp_number: str = "254716869648"

    # ── Pricing rules (mirror of PRICES.md — see CLAUDE.md before changing) ──
    # 0 = no floor. Mercy's call, 16 Aug 2026: "don't cap the price". The flyer's
    # numbers are the numbers. The mechanism is kept (not deleted) so a floor is a
    # config change if she ever wants one, but nothing imposes one by default.
    minimum_callout: int = 0
    recurring_discount_pct: int = 10
    recurring_requires_visit: bool = False

    # ── Lead store ──
    lead_store: Literal["memory", "sheets"] = "memory"
    sheet_id: str = ""
    google_service_account_json: str = ""

    # ── Quote reference counter ──
    quote_seq_path: str = "./data/quote_seq.json"

    # ── Rate limiting (POST /api/quote, per client IP) ──
    rate_limit_quote_per_min: int = 10
    rate_limit_quote_per_hour: int = 60

    # ── Business identity (stubs until Mercy registers — RECEIPTS_AND_INVOICING.md §5) ──
    business_legal_name: str = "pending registration"
    business_kra_pin: str = "pending"
    business_reg_no: str = "pending"
    vat_registered: bool = False
    vat_rate: int = 16

    # ── eTIMS (off until onboarded; OSCU issuance is Stage C, not v1) ──
    etims_enabled: bool = False
    etims_mode: Literal["manual", "oscu"] = "manual"
    etims_oscu_url: str = ""
    etims_oscu_key: str = ""
    etims_oscu_device_id: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
