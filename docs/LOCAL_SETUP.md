# CVOLVE PRO — Local Setup Guide

A practical, verified runbook for running this project on your own machine.

> **Verified 2026-07-13 against this machine:** Python **3.11.15** (`.venv`),
> PostgreSQL **14.23** client on `:5432`, all dependencies installed.

> **Status: almost everything is already done.** After the VPS recovery
> ([VPS_RECOVERY.md](VPS_RECOVERY.md)) the setup is wired up:
> - ✅ `.venv` built (Python 3.11 — native `tomllib`), `requirements.txt` installed
> - ✅ `payment.py` startup crash fixed (see §6.1 — kept for reference)
> - ✅ `.env` created and populated with recovered keys (Gemini/OpenAI/Resend/SMTP,
>   **Stripe TEST** keys, generated JWT secrets, pointing at the **local** DB)
> - ✅ `.streamlit/secrets.toml` created locally (`BASE_URL=localhost`, test keys)
> - ⏸️ **Only the database load remains** — deliberately deferred. See §3–§4: you can boot
>   the app against an **empty** DB right now (it self-bootstraps its schema); the full
>   182 MB data restore can wait.
>
> Related: [MISSING_FILES_AUDIT.md](MISSING_FILES_AUDIT.md) ·
> [VPS_RECOVERY.md](VPS_RECOVERY.md) · [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) ·
> [ROADMAP.md](ROADMAP.md)

---

## 1. What this project is

**CVOLVE PRO** is an AI resume/CV optimization platform. Two runnable entry points share the
same core modules (database, auth, payments, CV generation):

| Entry point | What it is | Command | Default port |
|---|---|---|---|
| `app.py` | Streamlit web UI (the main product) | `streamlit run app.py` | 8501 |
| `api_server.py` | FastAPI backend (Chrome extension / JobsQA / partners) | `uvicorn api_server:app --port 8000` | 8000 |

External services: **PostgreSQL** (all data), **Google Gemini / OpenAI** (generation),
**Stripe** (payments), **Resend** (email OTP on registration). You can run with just
**PostgreSQL + a Gemini key**; Stripe / Resend / OpenAI only gate their own features.

---

## 2. Prerequisites

- Python **3.11+** (already set up in `.venv`; 3.11 has native `tomllib`)
- PostgreSQL server running locally (this machine has **PostgreSQL 14.23** on `:5432`)
- `psql` / `createdb` client tools

Activate the environment:

```bash
source .venv/bin/activate     # or use .venv/bin/python directly
```

---

## 3. ⚠️ The one thing that blocks startup: the app needs a reachable database

**[app.py:282](../app.py#L282) calls `init_db()` at module load** — before any UI renders.
That opens a Postgres connection immediately, so **the Streamlit app cannot start at all if
Postgres is unreachable or the `cvolvepro` database / password is wrong.** This is the most
common "it won't start" cause and isn't obvious from the code.

The upside: `init_db()` is **idempotent** — it runs 12 `CREATE TABLE IF NOT EXISTS`
statements. So you do **not** need the big data dump just to boot: point it at an **empty**
`cvolvepro` database and it creates its own schema on first run.

That gives you two setup paths in §4 — pick one.

---

## 4. Database setup — pick one path

Both need a local Postgres role/password that matches `.env`
(`DB_USER=postgres`, `DB_PASSWORD=cvolve_local_2026`). Setting the password needs `sudo`
(peer auth), so run these yourself:

```bash
sudo -u postgres psql -c "ALTER ROLE postgres PASSWORD 'cvolve_local_2026';"
```

### Path A — Lightweight: empty DB, app self-bootstraps  *(recommended to see it run now)*

```bash
sudo -u postgres createdb -O postgres cvolvepro
# That's it. app.py's init_db() creates the CVolve tables on first launch.
```

You'll start with a clean database: register a fresh local user and test CV generation.
> Note: this creates the **CVolve** tables only — **not** the `jobsqa_*` tables (those come
> only from a full dump restore). Fine for working on the Streamlit app; the JobsQA API
> endpoints in `api_server.py` need Path B.

### Path B — Full data restore from the fresh production dump  *(deferred — do later)*

When you want real production data, restore the **fresh** dump taken during recovery (not
the stale bundled `cvolvepro.sql`):

```bash
sudo -u postgres createdb -O postgres cvolvepro        # if not already created
sudo -u postgres psql -d cvolvepro -f vps_recovery/cvolvepro_fresh_20260713.sql
```

This includes every table (CVolve **and** `jobsqa_*`) plus real users/payments. ~182 MB,
takes a minute. Skip `init_db()` — the dump already has the full schema.

> The dump was produced by a newer PostgreSQL and restores into 14; plain-SQL dumps normally
> restore fine across a version gap, but watch the output for errors.

---

## 5. Config files — already done ✅

Nothing to do here; documented so you know what's wired and where.

- **`.env`** (repo root, gitignored) — DB pointed at **local** Postgres, **Stripe TEST**
  keys, real Gemini/OpenAI/Resend/SMTP keys, generated `JWT_SECRET`/`FLASK_SECRET`.
  Both `app.py` and the modules call `load_dotenv()`, so it's read automatically.
- **`.streamlit/secrets.toml`** (gitignored) — needed because
  [app.py:1809](../app.py#L1809) reads `st.secrets.get("BASE_URL", ...)`; Streamlit errors
  if the file is absent. Local copy uses `BASE_URL=http://localhost:8501` and test keys.

> 🔒 The **live** Stripe keys and prod DB credentials live only in `vps_recovery/`
> (gitignored) for reference — local dev never uses them. Plan a key rotation with the client
> (the `sk_live` keys have been exported off the VPS during recovery).

Full list of variables the code reads: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `JWT_SECRET`,
`FLASK_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLIC_KEY`, `STRIPE_JOBSQA_WEBHOOK_SECRET`,
`RESEND_API_KEY`, `FROM_EMAIL`, `APP_FROM_EMAIL`, `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD`, `SMTP_FROM`, `CV_CREDIT_COST`, `CV_MAX_PAGES`, `DEFAULT_TEMPLATE`, `PORT`.

---

## 6. Run it (start to finish)

Everything before the database is already done. The remaining steps:

```bash
# 1. Set the local postgres password + create the DB (§4, Path A shown)
sudo -u postgres psql -c "ALTER ROLE postgres PASSWORD 'cvolve_local_2026';"
sudo -u postgres createdb -O postgres cvolvepro

# 2. Run the Streamlit UI (init_db() bootstraps the schema on first launch)
.venv/bin/streamlit run app.py
#    -> http://localhost:8501

# 3. (Optional) Run the FastAPI backend in a second terminal
.venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
#    -> http://localhost:8000   (health check: GET /health)
```

Quick sanity check that the DB is reachable before launching the UI:

```bash
.venv/bin/python -c "import database; database.get_connection(); print('DB connection OK')"
```

---

## 6.1 Historical blockers — already resolved (reference only)

These were real issues in the pre-recovery code, fixed now. Kept so the fixes are documented.

- **`payment.py` startup crash** — it used a bare `import tomllib` (3.11-only) and
  unconditionally opened `/opt/cvolvepro/CVOLVE-PRO/.streamlit/secrets.toml`. Now it guards
  the import and only opens that path `if os.path.exists(...)`, falling back to env vars —
  mirroring what `api_server.py` already did. (This is why the repo `payment.py` intentionally
  differs from the VPS copy; keep the repo version.)
- **No `.env.example`** — created during recovery; `.env` is built from it.

---

## 7. Quick reference — file map

| File | Role |
|---|---|
| `app.py` | Streamlit UI: login, register, CV generation, billing, analytics. **Runs `init_db()` at load — needs a live DB to start.** |
| `api_server.py` | FastAPI server for extension / JobsQA / partners |
| `database.py` | PostgreSQL connection, `init_db()` schema bootstrap, CRUD |
| `auth.py` | Email auth, session helpers |
| `payment.py` | Stripe checkout / subscriptions (startup fix applied — §6.1) |
| `cv_generator.py` | Resume parsing, CV / cover letter / interview Q&A, ATS scoring |
| `templates.py` | PDF export templates (`professional` only) |
| `utils.py` | Keyword optimization, Gemini wrapper, country dial codes |
| `styles.css` | Streamlit custom CSS |
| `vps_recovery/cvolvepro_fresh_20260713.sql` | Fresh 182 MB prod dump for Path B (gitignored) |
| `smtp_test.py` | Standalone SMTP test (not used by the app) |

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| App exits immediately with a `psycopg2` / connection error | `init_db()` at [app.py:282](../app.py#L282) can't reach Postgres. Do §4 (create DB + set password matching `.env`). |
| `psql: fe_sendauth: no password supplied` / `password authentication failed` | Local `postgres` role password doesn't match `.env`. Re-run the `ALTER ROLE ... PASSWORD` from §4. |
| `StreamlitSecretNotFoundError` / secrets error | Missing `.streamlit/secrets.toml` (see §5). It should already exist; recreate if deleted. |
| App starts but CV generation fails | Missing/invalid `GEMINI_API_KEY` in `.env`. |
| Billing tab uses real money | It shouldn't — `.env` uses `sk_test_` keys. If you see `sk_live_`, stop and fix `.env`. |
| No OTP email on register | `RESEND_API_KEY` missing/invalid — expected if unset. |
| `ModuleNotFoundError: No module named 'tomllib'` | Only on Python <3.11 with an unpatched `payment.py`. Not applicable here (3.11 + fix applied). |
