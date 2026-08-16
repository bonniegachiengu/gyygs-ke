# Myra — Quote Calculator (v0 of gyygs.ke)

Phone-first cleaning quote tool. A customer self-quotes, then hands off to WhatsApp with the
job already scoped and priced. API-first, evolvable — **NOT a throwaway**.

## Stack

- **Backend:** Python 3.11 + FastAPI (Pydantic v2). Pure pricing engine. API-first.
- **Frontend:** React 19 + Vite + TypeScript + Tailwind v4 (SPA). Consumes the generated
  OpenAPI TS client only (`openapi-typescript` + `openapi-fetch`). Served by nginx on `:3000`,
  which also reverse-proxies `/api/*` → `api:8000`.
- **Data:** Google Sheets via a GCP service account (NO Apps Script), behind `LeadRepository`.
  Postgres later — same interface, new implementation.
- **Deploy:** Docker Compose (`api`, `web`, `cloudflared`) → Cloudflare **named** tunnel
  (`myra`, credentials-file auth) → `myra.vyybandasky.online`.

## Rules

- Pricing is **server-authoritative**; values come from `PRICES.md` (mirrored in
  `domain/pricing_data.py`). Never trust a client-sent total — `QuoteRequest` uses
  `extra="ignore"` so a posted `total` is silently dropped.
- **Transport is always separate** — never a line, never added to the subtotal, always a note.
- Any `from` / `quote` / `visit` / ranged item ⇒ `visit_first=true`, no hard total. A range
  contributes its **lower bound**; the full range goes in the line label.
- Modifiers are **additive** (`+300`), not multiplicative. `ARCHITECTURE §6`'s `×(1+m)` prose
  is contradicted by its own `§5` data and by `PRICES.md §F`. The two coincide on a 5×7 carpet
  (1000+300 = 1000×1.3 = 1300) — assert on a 6×9 instead (1600, not 1690).
- Secrets never in the repo (service-account JSON, tunnel credentials) — runtime-injected,
  gitignored.
- Pricing engine must have pytest coverage. Worked example:
  3-seat sofa 1,500 + mattress 5×6 1,500 + fridge 800 = **KSh 3,800** (Ruiru).
- Contracts (`/api/pricing`, `/api/quote`) are fixed — `ARCHITECTURE.md §5`. Field names are
  the contract; the frontend consumes them through the generated client.
- **Don't build:** eTIMS/OSCU API, accounts, payments, booking, worker features. Later phases.

## Decisions taken at kickoff (2026-08-16)

| Decision | Value |
|---|---|
| Frontend framework | React + Vite + Tailwind (matches the VOS III stack Bonnie maintains) |
| Minimum call-out | **None. `MINIMUM_CALLOUT=0`.** Mercy, 16 Aug 2026: *"don't cap the price, so no 1000 or 1500 or any other cap."* The flyer's numbers are the numbers. Sofa `min_units` dropped to 1 for the same reason. The floor mechanism is kept so it is a config change if ever revisited. |
| Recurring | **Premises decides.** Office / commercial / post-construction / BnB → site visit. Residential recurring → −10% and a real total. `RECURRING_REQUIRES_VISIT=false`. |
| Tunnel | New named tunnel `myra`, created by CLI against the existing zone cert. No Zero Trust dashboard. |

## Open — needs Mercy (Friday)

- `RECURRING_DISCOUNT_PCT=10` is a **placeholder**. `FRIDAY_WITH_MERCY.md §3`: *"You set the number."*
- **The discount is self-declared and unearned.** `recurring` is a checkbox on the Where&When
  screen; anyone can tick it and take 10% off a one-off job, on their first booking, with
  nothing given in return. At a 50–55% gross margin, 10% off list is ~20% of the gross margin.
  Nothing verifies the customer ever comes back. Recommendation on the table — do not treat
  the current behaviour as settled.
- Business identity stubs (`BUSINESS_LEGAL_NAME`, `BUSINESS_KRA_PIN`, `BUSINESS_REG_NO`) stay
  "pending registration" until the eCitizen/KRA steps in `REGISTRATION.md` are done.

## Build order

M0 pipe (health + tunnel) → M1 product (engine + calculator + WhatsApp handoff) →
M2 Sheets log → M2.5 receipts → M3 ship. Commit in small steps; run tests before calling a
milestone done; report progress so `WBD_SPEC_TRACKER.md` stays current.

## Docs (source of truth — live in `…\Projects\Gigs\`, read-only from here)

- `ARCHITECTURE.md` — tech contract  · `QUOTE_CALCULATOR_SPEC.md` — UX
- `PRICES.md` — prices               · `RECEIPTS_AND_INVOICING.md` — M2.5
- `DISPATCH_BRIEF.md` — milestones   · `WBD_SPEC_TRACKER.md` — status
