# Missing Files Audit

What this repo has, what it's missing, where each missing piece lives, and how to recover
it. Produced by a full scan of every import and file-path reference in the codebase
(2026-07-13). Recovery steps are in [VPS_RECOVERY.md](VPS_RECOVERY.md).

## Verdict up front

**The Python code is complete.** Every local import (`database`, `auth`, `payment`,
`cv_generator`, `templates`, `utils`) resolves to a file in the repo. Nothing needed to
*run the backend* is missing except **credentials/config** and a handful of
**deployment-side assets** that live on the VPS.

---

## 1. Missing — recover from the VPS

> **Update 2026-07-13:** all five items below were **located during recon** (paths/content
> confirmed). They just need pulling to local files via `scripts/vps_pull.sh`. Note item 3
> is `payment-success.html`, not `index.html`.

| # | File | Referenced by | Impact | Where to find it |
|---|---|---|---|---|
| 1 | `.streamlit/secrets.toml` | `payment.py:24` *(was a hard crash — now patched to optional)*, `api_server.py:32` (graceful), `app.py:1809` (`st.secrets` for `BASE_URL`) | Holds **all production keys**: Stripe, Gemini, OpenAI, Resend, JWT | `/opt/cvolvepro/CVOLVE-PRO/.streamlit/secrets.toml` |
| 2 | `.env` (production) | `load_dotenv()` in `app.py`, `utils.py`, `cv_generator.py`; `smtp_test.py:6` | Same credential set, env-var form (may or may not exist on VPS — secrets.toml may be the only source) | `/opt/cvolvepro/CVOLVE-PRO/.env` (check) |
| 3 | `index.html` (Stripe "success hop" page) | `app.py:1765` redirect logic (`:1636`) | Stripe checkout return flow breaks without it in prod | nginx web root on VPS (`/var/www/...` — find via nginx config) |
| 4 | nginx site config(s) | — (deployment sketch in ARCHITECTURE.md only) | Can't understand/redeploy routing + SSL without it | `/etc/nginx/sites-enabled/` |
| 5 | systemd unit files (or supervisor/pm2 config) | — | How Streamlit + Uvicorn actually run/restart | `/etc/systemd/system/*.service` (see recon) |

## 2. Missing — request from the client (not on the VPS)

> **Update 2026-07-13:** recon changed this section — items 6 and 7 are **both actually on
> the VPS**, so they're recoverable, not client asks. Only the Web-Store account (6) and
> account-access list (8) still need the client.

| # | Item | Why it matters |
|---|---|---|
| 6 | ~~**Chrome extension source**~~ **Found on VPS** at `/opt/cvolvepro/cvolvepro-extension/` (+ `.crx` + `cvolvepro-keys/`). Only the client's Chrome **Web Store account** is still needed to publish updates |
| 7 | ~~**jobsqa.com frontend**~~ **Co-hosted on this VPS** — nginx serves `jobsqa.com`/`api.jobsqa.com` from `/opt/cvolvepro/frontend-interview`. Still confirm who *owns* the domain/account with the client |
| 8 | Account access list | Stripe, Resend, Google AI Studio, OpenAI, DNS registrar, Hostinger panel, Chrome Web Store — full list in [SYSTEM_ARCHITECTURE.md §5](SYSTEM_ARCHITECTURE.md) |

## 3. Not missing — resolved or ignorable

| Item | Status |
|---|---|
| Local Python modules | ✅ all present; `from app ...` strings in `api_server.py:107,529` are comments, not imports |
| `styles.css`, `logo.jpeg` | ✅ present (`app.py:326`, `app.py:318`) |
| `users.db` | 🗑️ **dead SQLite leftover** from an earlier prototype — nothing references `sqlite3` or `users.db`; gitignored; safe to ignore |
| `.streamlit/config.toml` | Never referenced by code — not needed |
| Database schema | ✅ `cvolvepro.sql` is a **superset** of every table the code uses (incl. all `jobsqa_*` tables + extras `business_credit_usage`, `business_subscriptions`, `jobsqa_payments`). Restoring the dump = complete schema; skip `init_db()` |
| `.env.example` | ✅ now created in repo root (was referenced by docs but absent) |

### ⚠️ Schema caveat

`database.init_db()` creates the CVolve tables but **not** the `jobsqa_*` tables. Never
bootstrap a fresh DB with `init_db()` alone — always restore from a dump (ideally a fresh
one from production, see [VPS_RECOVERY.md §3.1](VPS_RECOVERY.md)).

### ⚠️ Data staleness

The bundled `cvolvepro.sql` (182 MB) is a snapshot from whenever it was dumped. Production
keeps accruing users/payments — treat the **live DB as the source of truth for data** and
re-dump before anything that matters.

---

## 4. Recovery status checklist

**Recon (Phase A) completed on the VPS 2026-07-13** — see `docs/Vps recvoery results.pdf`
(gitignored; contains live keys). Almost everything is now *located/captured*; what remains
is pulling it to local files via `scripts/vps_pull.sh` (Phase B, run from your laptop).

- [x] `.env.example` created in repo
- [x] `payment.py` patched (no longer crashes without VPS secrets file)
- [x] `.streamlit/secrets.toml` **recovered** (all prod keys captured in recon) — ⏳ still
      need to copy values into local `.env`
- [x] Production `.env` **located** on VPS (322 B, confirms `DB_HOST=127.0.0.1`) — ⏳ pull pending
- [x] Stripe success page **located** — it's `payment-success.html` in
      `/opt/cvolvepro/frontend-interview/` (nginx `location = /payment-success`), **not**
      the `index.html` originally guessed — ⏳ pull pending
- [x] nginx configs **captured** in recon (full content) — ⏳ pull to files pending
- [x] systemd units **identified**: `cvolvepro.service` (Streamlit :8502) +
      `cvolvepro_api.service` (FastAPI :8000) — ⏳ pull pending
- [ ] Code drift check: VPS deploy dir diffed against this repo
- [ ] Fresh production `pg_dump` taken (Postgres is **local** on the VPS)
- [x] Chrome extension source — **found ON the VPS** (`/opt/cvolvepro/cvolvepro-extension/`
      + `cvolvepro-extension.crx` + `cvolvepro-keys/`); no need to request from client — ⏳ pull pending
- [x] jobsqa.com — **co-hosted on this same VPS** (nginx `jobsqa.com` / `api.jobsqa.com`,
      root `/opt/cvolvepro/frontend-interview`); still confirm ownership/Web-Store account with client
- [ ] Account access list requested from client

### 🔎 Other recon findings (2026-07-13)

- **⚠️ No backup exists** — `crontab -l` returned `no crontab for root`; nothing is dumping
  the production DB. Set up a nightly `pg_dump` cron ASAP (Phase 1).
  ⚠️ Backup situation: NONE today — crontab -l = no crontab for root. Set up a nightly pg_dump cron ASAP (Phase 1); see SYSTEM_ARCHITECTURE.md
- **Shared multi-app box** — the VPS also runs **orbynecue/orbyneai** (ports 8001, 5002,
  8081) and the jobsqa frontends. Never reload nginx / restart services casually.
- **Clean code snapshot exists**: `CVOLVE-PRO-source.tar.gz` (606 KB, Jul 11) sits in the
  deploy dir.
- **⚠️ Live `sk_live` Stripe keys** now exist outside the VPS (in the recovery PDF) — plan a
  key rotation with the client during Phase 1.
