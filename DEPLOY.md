# Deploying Myrah

Two environments, one machine, one repo. Everything below was learned by
getting it wrong at least once; the incidents are named so the rules are
arguable rather than cargo-culted.

| | Production | Staging |
|---|---|---|
| Worktree | `dev\gyygs.ke` | `dev\gyygs.ke-staging` |
| Branch | `main` | `staging` (+ feature branches) |
| Web / API | `:3000` / `:8010` | `:3001` / `:8011` |
| Hostnames | `myrah.*`, `myrahcleaning.*` (+ `myra.*` → 301) | `staging-myrah.*` |
| Database | `data/leads.db` | `data/staging/leads.db` |
| WhatsApp | the real business line, via its own `.env` | the **test** line |

**The promote path is one-way:** build → deploy to staging → prove there →
deliberate cutover to production. Never an in-place edit on production.

---

## ★ The promote checklist

Work down it. The two starred steps are the ones that have actually bitten.

- [ ] **1. Prove it on staging first.** Not on a fixture — through the real
      public staging URL. Unit tests passed while a KSh 3,800 job asked for a
      "KSh 11 deposit"; only an end-to-end run exposed it.

- [ ] **2. Merge to `main`, don't cherry-pick loosely.** Check what the branch's
      *lineage* carries. Two approved brand commits sat on branches that also
      contained an unapproved feature; merging would have shipped it.

- [ ] **3. Read the promote diff.** Not skim — read. A cherry-pick that predated
      a safety fix silently reinstated Mercy's real phone number as a code
      default, and the guard that catches it lived on another branch.

- [ ] **4. Rebuild the frontend.** `npm run build -w apps/web`.
      nginx serves `dist/` from disk per request, so this alone makes static
      changes live — no service cycle needed.

- [ ] **★ 5. If ANY Python changed, CYCLE `Myra-API`.**
      **A rebuild is not enough.** nginx re-reads `dist` per request; the API
      loads its code once at start and holds it in memory. Skip this and the
      promote goes half-live: the page updates, the API does not.

      This bit us on the single most customer-visible string we have. The
      rebrand shipped, the page read "Myrah", and every WhatsApp quote kept
      greeting customers as **"Hi Myra Cleaning"** — because the API process
      predated the promote.

      ```powershell
      .\infra\restart-verified.ps1 -ServiceName Myra-API -ChildProcess python
      ```

      Use that, not `Restart-Service`. See §"Restarts lie" below.

- [ ] **6. If any nginx or tunnel config changed, cycle that service too** —
      same reason, same script. `Myra-Nginx`, `Cloudflared-Myra`.

- [ ] **7. Verify from the OUTSIDE.** Not `127.0.0.1`, not a Host header — the
      real public URL, which is the only thing that exercises DNS, the tunnel,
      nginx and the API together.

- [ ] **8. Check every hostname, not just the one you changed.**
      `myrah` · `myrahcleaning` · `myra` (301) · `myracleaning` (301) ·
      `staging-myrah` · `lg` · `launchgear` · `app` · `sustena/health`

- [ ] **9. Confirm staging is still separate** — different `APP_VERSION`,
      different database. A promote must not merge the two.

---

## Restarts lie

`Restart-Service` can return, report `Running`, and have done **nothing**.

These services grant start/stop to SYSTEM and Administrators only; an
unelevated call fails with *"Cannot open <service> service on computer '.'"*.
With `$ErrorActionPreference = 'SilentlyContinue'` that error vanishes, and
`Status` still reads `Running` — because it never stopped.

An edited tunnel config sat unapplied for two hours that way while every check
said it was fine.

> **`Status -eq 'Running'` does not mean a restart happened.** It means
> something is running — possibly the same process, still holding the old code
> or config in memory.

`infra\restart-verified.ps1` is the fix: it checks elevation up front, refuses
loudly rather than discovering it through a swallowed error, and **proves the
cycle by comparing child PIDs before and after**. A surviving PID fails the
script.

`infra\grant-service-control.ps1` — run **once, elevated** — grants this
machine's interactive user start/stop on the five native services, after which
none of this needs elevation.

---

## Things that must live on `main`

Production runs from the `main` worktree, so **every file a running service
touches must be tracked on `main`** — not on a feature branch, not only in the
staging worktree.

This has caught us twice:

- `infra/nginx-windows.conf` vanished from the prod worktree on a `git checkout
  main`, because it was tracked on a feature branch. nginx kept serving only
  because it had already read the config into memory. The next restart — a
  reboot, a crash, nssm's own auto-restart — would have taken `myrah.*` and
  `lg.*` down with no obvious cause.
- `infra/grant-service-control.ps1` existed only in the staging worktree, so
  the documented command failed with *"is not recognized"*.

**Rule:** if you write an ops script or a service config, land it on `main` in
the same session. If production needs it, `main` has it.

---

## Brand and phone numbers

- **Brand strings are capitalised**: `Myra`/`MYRA` → `Myrah`/`MYRAH`.
  Lowercase `myra` is *never* the brand — it is only the retired redirect-source
  domain (`myra.vyybandasky.online`) or an infra identifier (the tunnel is named
  `myra`; the services are `Myra-API`, `Myra-Nginx`, `Cloudflared-Myra`).
  Renaming those is an infrastructure migration, not a text edit.
- **Mercy's real line must never appear in committed source**, including
  defaults, fixtures and comments. Production supplies it through its own
  gitignored `.env`. `tests/test_job_spine.py::TestNoRealNumberInTests` greps
  the whole repo for it — that guard found six violations on its first run,
  including a code default and the committed `.env.example`.

---

## Commands

```powershell
# staging (unelevated — these processes are not services)
cd C:\Users\DELL\dev\gyygs.ke-staging
npm run build -w apps/web
# then restart the :8011 python and the nginx-staging.conf instance

# production
cd C:\Users\DELL\dev\gyygs.ke
git merge --no-ff <approved-branch>
npm run build -w apps/web
.\infra\restart-verified.ps1 -ServiceName Myra-API   -ChildProcess python      # if Python changed
.\infra\restart-verified.ps1 -ServiceName Myra-Nginx -ChildProcess nginx       # if nginx conf changed
```
