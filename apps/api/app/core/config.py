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
    # complex-typed env vars, and `CORS_ORIGINS=https://myrah.vyybandasky.online` is not
    # valid JSON — declaring it as a list raises SettingsError at import time.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    public_site_host: str = "myrah.vyybandasky.online"

    # ── WhatsApp handoff ──
    whatsapp_number: str = "254754413351"

    # ── Pricing rules (mirror of PRICES.md — see CLAUDE.md before changing) ──
    # 0 = no floor. Mercy's call, 16 Aug 2026: "don't cap the price". The flyer's
    # numbers are the numbers. The mechanism is kept (not deleted) so a floor is a
    # config change if she ever wants one, but nothing imposes one by default.
    minimum_callout: int = 0
    recurring_discount_pct: int = 10
    recurring_requires_visit: bool = False
    # 2 = full price on the first clean, discount from the second. 1 would give it
    # away on a self-declared checkbox with nothing earned.
    recurring_discount_from_job: int = 2

    # ── Lead store ──
    # "sqlite" is the durable store for the native (no-Docker) deployment: one
    # local file, no extra service to supervise. "memory" loses every lead on
    # restart and is only appropriate for tests and throwaway runs.
    lead_store: Literal["memory", "sheets", "sqlite"] = "memory"
    sheet_id: str = ""
    google_service_account_json: str = ""
    # Only read when lead_store == "sqlite". Sits beside quote_seq_path so the
    # API's entire durable footprint is one directory.
    lead_db_path: str = "./data/leads.db"

    # ── Operator surface (Phase A) ──
    # A shared PIN to start, exactly as MYRAH_WHATSAPP_AND_CMS.md §3d says:
    # "start with a shared PIN; proper auth later". Empty means the admin
    # routes refuse with 503 rather than defaulting to something guessable.
    admin_pin: str = ""
    # 30% to hold a slot -- MYRAH_OPERATIONS_DESIGN.md §11 decision 1.
    # Config, not a literal, so Mercy can change it without a code change.
    deposit_pct: int = 30


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
