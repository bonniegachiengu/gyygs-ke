# Myra Quote Calculator — v0 of gyygs.ke

A phone-first web app where a customer self-quotes cleaning services and hands off to WhatsApp
with the job already scoped and priced. Built as the first brick of the **gyygs.ke** platform:
typed end-to-end, server-authoritative pricing, repository-backed persistence, containerized.

Live at **https://myra.vyybandasky.online** · WhatsApp handoff to **0716 869 648**

## Layout

```
apps/api    FastAPI service — pricing engine, quote contract, lead repository
apps/web    React + Vite SPA — the calculator; consumes the generated OpenAPI client
packages/   contracts (openapi.json, catalogue snapshot) + shared engine fixtures
infra/      docker-compose (api · web · cloudflared) and the tunnel config
```

Specs are the source of truth and live outside this repo, in `…\Projects\Gigs\`:
`ARCHITECTURE.md` (contracts), `QUOTE_CALCULATOR_SPEC.md` (UX), `PRICES.md` (prices),
`DISPATCH_BRIEF.md` (milestones), `WBD_SPEC_TRACKER.md` (status). See `CLAUDE.md` for the
working rules and the decisions taken at kickoff.

## Local development

No Docker needed for the day-to-day loop.

```bash
# terminal A — the API
cd apps/api
py -3.11 -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8010

# terminal B — the web app, from the repo root
npm install
npm run dev                                            # http://localhost:5173
```

> **Port 8010, not 8000.** On Bonnie's machine WSL forwards `localhost:8000` to the VOS III
> backend, which runs live M-Pesa capture. Myra uses 8010 everywhere — local dev, the container,
> and the nginx upstream — so the two projects can run side by side.

Vite proxies `/api/*` to `127.0.0.1:8010`, and nginx does the same in production — so the
frontend calls the API same-origin in both worlds and there is no `VITE_API_BASE` to get wrong.
`npm run dev` binds all interfaces, so a real Android phone on the same Wi-Fi can hit
`http://<your-lan-ip>:5173` for QA.

**Preflight** (guards against the stray `C:\Users\DELL\package.json` / `node_modules` above this
repo shadowing a missing dependency):

```bash
node -e "console.log(require.resolve('react'))"        # must print a path under dev/gyygs.ke
```

Never run `npm install` from a directory above `dev/gyygs.ke`.

## Tests

```bash
cd apps/api && pytest        # pricing engine + API. The gate on revenue correctness.
npm run build                # tsc -b — a contract drift is a compile error
npm run test                 # vitest — the client estimator against the shared fixtures
```

`packages/fixtures/golden_quotes.json` is consumed by **both** pytest and vitest, so the Python
engine and the TypeScript live estimator cannot drift apart.

## Typed contract

FastAPI owns the schema. Regenerate the client after any API change:

```bash
npm run gen        # export openapi.json, then generate apps/web/src/lib/api/schema.d.ts
npm run gen:check  # CI: fails if the committed client disagrees with the API
```

`schema.d.ts` is generated **and committed** so a fresh clone typechecks without Python. Never
hand-edit it.

## Deploy

```bash
cd infra
docker compose build
docker compose up -d
docker compose logs -f cloudflared
```

Requires Docker Desktop running, `../.env` filled in from `.env.example`, and the tunnel
credentials in place (below). `web` is published on `:3000` for LAN phone QA; `api` is not
published at all — only `web` can reach it.

### Cloudflare tunnel (one-time)

The zone `vyybandasky.online` is already on Cloudflare and `~/.cloudflared/cert.pem` (in WSL)
carries the authority, so this needs no Zero Trust dashboard:

```bash
cloudflared tunnel create myra                                   # prints <UUID>, writes <UUID>.json
cloudflared tunnel route dns myra myra.vyybandasky.online        # creates the CNAME
```

Copy **only** `~/.cloudflared/<UUID>.json` into `infra/cloudflared/` (gitignored) and put the
UUID into `infra/cloudflared/config.yml`. Do **not** copy `cert.pem` — it is zone-wide authority
and the running tunnel does not need it.

## Staying up

The site is served from Bonnie's laptop, so "is it running" is a real operational
question. Two mechanisms, one inside Docker and one outside it:

- `restart: unless-stopped` on every service — a crashed container comes back on
  its own, and all three restart automatically once the engine is available.
- **`infra/watchdog.ps1`**, run by the `Myra site watchdog` scheduled task at
  logon and every 5 minutes thereafter.

The watchdog checks the **public URL end to end**, not a local process. That is
deliberate: the failure mode this project has actually seen is `cloudflared`
alive but not serving, which every process-level check reports as healthy. Only
a real request through Cloudflare proves a customer can reach the site.

It is silent when healthy. When it has to intervene it logs to `logs/watchdog.log`
and pushes a notification to the ntfy topic in `infra/.ntfy-topic` (both
gitignored).

Install or reinstall the task — no admin rights needed, and safe to re-run:

```powershell
powershell -ExecutionPolicy Bypass -File infra/install-watchdog.ps1
```

Force a recovery run for testing, even when the site looks fine:

```powershell
powershell -ExecutionPolicy Bypass -File infra/watchdog.ps1 -Force
```

### The one gap this cannot close

Docker Desktop on Windows is a per-user GUI app: it needs a **logged-on
session**. If the machine reboots and sits at the lock screen without anyone
signing in, neither trigger fires and the site stays down. Windows Update
reboots are the usual cause — the 18 Aug 2026 outage was exactly this.

Two ways out, when it matters enough: turn on Windows' *"Use my sign-in info to
automatically finish setting up my device after an update"*, or move the stack
into WSL beside VOS III, where `systemd` + `loginctl enable-linger` already
survives logout. The second is the real fix.

## Secrets

Nothing secret is committed. `.env`, `secrets/*.json` and `infra/cloudflared/*.json` are
gitignored and injected at runtime. `.env.example` documents every key.
