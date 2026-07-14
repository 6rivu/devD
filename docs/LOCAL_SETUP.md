# CVOLVE PRO — Local Setup Guide

A practical, verified runbook for running this project on your own machine.

> **Verified 2026-07-15 against this machine:** Python **3.11.15** (`.venv`),
> app database = **Docker PostgreSQL 16** (`cvolve-pg`) on **`:5433`**, full production
> dump restored (1,417 users / 18 tables), both new features (Job Aggregator + CV↔JD
> Alignment) integrated and end-to-end tested, **47/47 unit tests green**.

> **Status: setup is complete — the app runs against real data right now.** After the VPS
> recovery ([VPS_RECOVERY.md](VPS_RECOVERY.md)) everything is wired:
> - ✅ `.venv` built (Python 3.11 — native `tomllib`), `requirements.txt` installed
> - ✅ `payment.py` startup crash fixed (see §7.1 — kept for reference)
> - ✅ `.env` created and populated with recovered keys (Gemini/OpenAI/Resend/SMTP,
>   **Stripe TEST** keys, generated JWT secrets, Adzuna keys), pointing at the **local**
>   Docker DB on `:5433`
> - ✅ `.streamlit/secrets.toml` created locally (`BASE_URL=localhost`, test keys)
> - ✅ **Database restored** — the fresh 182 MB production dump is loaded into a Docker
>   PostgreSQL 16 container (§4). The app connects to it and works.
>
> Related: [MISSING_FILES_AUDIT.md](MISSING_FILES_AUDIT.md) ·
> [VPS_RECOVERY.md](VPS_RECOVERY.md) · [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) ·
> [ROADMAP.md](ROADMAP.md) · [JOB_AGGREGATOR_PLAN.md](JOB_AGGREGATOR_PLAN.md) ·
> [CV_JD_ALIGNMENT_PLAN.md](CV_JD_ALIGNMENT_PLAN.md)

---

## 1. What this project is

**CVOLVE PRO** is an AI resume/CV optimization platform. Two runnable entry points share the
same core modules (database, auth, payments, CV generation):

| Entry point | What it is | Command | Default port |
|---|---|---|---|
| `app.py` | Streamlit web UI (the main product) | `streamlit run app.py` | 8501 |
| `api_server.py` | FastAPI backend (Chrome extension / JobsQA / partners) | `uvicorn api_server:app --port 8000` | 8000 |

External services: **PostgreSQL** (all data), **Google Gemini / OpenAI** (generation),
**Stripe** (payments), **Resend** (email OTP on registration), **Adzuna** (one of the job
sources). You can run with just **PostgreSQL + a Gemini key**; Stripe / Resend / OpenAI /
Adzuna only gate their own features.

**Two features added on top of the recovered base (both tested locally):**
- **Phase 1 — Job Aggregator** ([job_aggregator.py](../job_aggregator.py)): pulls live jobs from
  Remotive + Arbeitnow (keyless) and Adzuna (keyed), dedupes, and scores them by keyword
  overlap with the user's résumé. Surfaced as a tab in `app.py`; costs 1 credit per search.
- **Phase 2 — CV↔JD Alignment** ([cv_generator.py](../cv_generator.py)): one LLM call finds gaps
  between a résumé and a target job description and asks the user follow-up questions; the
  verified answers enrich the CV / cover letter / interview prep. Answers persist in
  `user_sessions` keyed by JD hash.

---

## 2. Prerequisites

- Python **3.11+** (already set up in `.venv`; 3.11 has native `tomllib`)
- **Docker** (Docker Desktop) — the app's PostgreSQL 16 runs in a container (see §4 for why)
- `psql` client is optional (you can run everything through `docker exec`)

Activate the environment:

```bash
source .venv/bin/activate     # or use .venv/bin/python directly
```

---

## 3. ⚠️ The one thing that blocks startup: the app needs a reachable database

**[app.py](../app.py) calls `init_db()` at module load** — before any UI renders. That opens a
Postgres connection immediately, so **the Streamlit app cannot start at all if Postgres is
unreachable or the `cvolvepro` database / password / port is wrong.** This is the most common
"it won't start" cause and isn't obvious from the code.

On this machine the database is already up (§4). If you ever see a `psycopg2` connection error
on launch, the container is probably stopped — `docker start cvolve-pg`.

---

## 4. Database — Docker PostgreSQL 16 on `:5433` (already restored ✅)

### 4.0 Why Docker, and why port 5433

This machine already has a **native PostgreSQL 14 on `:5432`** used by other things — it is
**left untouched**. The production dump
(`vps_recovery/cvolvepro_fresh_20260713.sql`) was taken from PostgreSQL 16 and uses the
`\restrict` directive, which **PostgreSQL 14 cannot restore**. So the app's database runs in a
**PostgreSQL 16 Docker container mapped to host port `:5433`**, and `.env` points there
(`DB_PORT=5433`). The two servers coexist; nothing about the native `:5432` install changes.

### 4.1 Current state (nothing to do — documented for reference)

| Thing | Value |
|---|---|
| Container | `cvolve-pg` (image `postgres:16`) |
| Host port | `5433` → container `5432` |
| Named volume | `cvolve_pgdata` (data survives container restarts) |
| Database | `cvolvepro` (owner role `cvolvepro_app` pre-created) |
| App connects as | `postgres` / `cvolve_local_2026` |
| Restored from | `vps_recovery/cvolvepro_fresh_20260713.sql` (182 MB, ~176 MB in DB) |
| Contents | 18 tables, 1,417 users, 3,103 cv_generations, 4,849 credit_usage, 1,187 user_sessions |

Start it if it's stopped (Docker Desktop runs as a **user** service here — note `--user`):

```bash
systemctl --user start docker-desktop   # if Docker isn't running yet
docker start cvolve-pg                   # start the DB container
docker ps --filter name=cvolve-pg        # confirm: Up ... 0.0.0.0:5433->5432/tcp
```

> This user is **not** in the `docker` group and the default CLI context is `desktop-linux`.
> If `docker` commands can't reach the daemon, start Docker Desktop first (line above).

### 4.2 How to reproduce the restore from scratch (only if the volume is lost)

```bash
# 1. Run a Postgres 16 container on host :5433 with a persistent volume
docker run -d --name cvolve-pg \
  -e POSTGRES_PASSWORD=cvolve_local_2026 \
  -p 5433:5432 -v cvolve_pgdata:/var/lib/postgresql/data \
  postgres:16

# 2. Create the database and the dump's owner role
docker exec -i cvolve-pg psql -U postgres -c "CREATE DATABASE cvolvepro;"
docker exec -i cvolve-pg psql -U postgres -c "CREATE ROLE cvolvepro_app;"

# 3. Restore the fresh production dump (NOT the stale bundled cvolvepro.sql)
docker exec -i cvolve-pg psql -U postgres -d cvolvepro \
  < vps_recovery/cvolvepro_fresh_20260713.sql
```

> Expect ~16 harmless `GRANT`/`ROLE` errors for a missing `powerbi_user` reporting role —
> cosmetic, the app connects as `postgres`. The dump uses `\restrict`, so it **must** be
> restored with `psql` **16+** (that's the whole reason for the Docker PG16 container).

### 4.3 Lightweight alternative — empty DB, app self-bootstraps

If you don't need production data, `init_db()` runs 12 `CREATE TABLE IF NOT EXISTS`
statements, so an empty `cvolvepro` database is enough to boot:

```bash
docker exec -i cvolve-pg psql -U postgres -c "CREATE DATABASE cvolvepro;"
# app.py's init_db() creates the CVolve tables on first launch.
```

> This creates the **CVolve** tables only — **not** the `jobsqa_*` tables (those come only
> from the full dump). Fine for the Streamlit app; the JobsQA API endpoints in
> `api_server.py` need the full restore (§4.2).

---

## 5. Config files — already done ✅

Nothing to do here; documented so you know what's wired and where.

- **`.env`** (repo root, gitignored) — DB pointed at the **local Docker Postgres**
  (`DB_HOST=127.0.0.1`, **`DB_PORT=5433`**, `DB_NAME=cvolvepro`, `DB_USER=postgres`,
  `DB_PASSWORD=cvolve_local_2026`), **Stripe TEST** keys, real Gemini/OpenAI/Resend/SMTP keys,
  **Adzuna** keys (`ADZUNA_APP_ID` / `ADZUNA_APP_KEY`) for the job aggregator, and generated
  `JWT_SECRET`/`FLASK_SECRET`. Both `app.py` and the modules call `load_dotenv()`, so it's
  read automatically.
- **`.streamlit/secrets.toml`** (gitignored) — needed because `app.py` reads
  `st.secrets.get("BASE_URL", ...)`; Streamlit errors if the file is absent. Local copy uses
  `BASE_URL=http://localhost:8501` and test keys.

> 🔒 The **live** Stripe keys and prod DB credentials live only in `vps_recovery/`
> (gitignored) for reference — local dev never uses them. Plan a key rotation with the client
> (the `sk_live` keys have been exported off the VPS during recovery).

Full list of variables the code reads: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ADZUNA_APP_ID`,
`ADZUNA_APP_KEY`, `JWT_SECRET`, `FLASK_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLIC_KEY`,
`STRIPE_JOBSQA_WEBHOOK_SECRET`, `RESEND_API_KEY`, `FROM_EMAIL`, `APP_FROM_EMAIL`,
`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `CV_CREDIT_COST`,
`CV_MAX_PAGES`, `DEFAULT_TEMPLATE`, `PORT`.

---

## 6. Run it (start to finish)

Everything is already set up. The full sequence from a cold machine:

```bash
# 1. Make sure the database is running (§4)
systemctl --user start docker-desktop   # only if Docker isn't already up
docker start cvolve-pg

# 2. (Optional) Sanity-check the DB is reachable before launching the UI
.venv/bin/python -c "import database; database.get_db_connection(); print('DB connection OK')"

# 3. Run the Streamlit UI (init_db() bootstraps/verifies the schema on launch)
.venv/bin/streamlit run app.py
#    -> http://localhost:8501

# 4. (Optional) Run the FastAPI backend in a second terminal
.venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
#    -> http://localhost:8000   (health check: GET /health)
```

### 6.1 Run the tests

The two new features ship with a stdlib `unittest` suite (no network, no DB required):

```bash
.venv/bin/python -m unittest discover -s tests
#    -> Ran 47 tests ... OK
```

### 6.2 Exercising the two features

- **Job Aggregator** — open the job-search tab in the UI, enter a title (e.g. "python
  developer") and country, and search. Needs the `ADZUNA_*` keys for the Adzuna source;
  Remotive + Arbeitnow work without any key. Each search costs 1 credit (only charged if at
  least one source was reachable).
- **CV↔JD Alignment** — paste a job description alongside a résumé; the tool runs one LLM call
  (needs a valid `GEMINI_API_KEY` or `OPENAI_API_KEY`) to surface gap questions. Answering is
  optional (skip-allowed); answers are saved per JD and reused across CV / cover letter /
  interview prep.

---

## 7. Historical blockers — already resolved (reference only)

These were real issues in the pre-recovery code, fixed now. Kept so the fixes are documented.

- **`payment.py` startup crash** — it used a bare `import tomllib` (3.11-only) and
  unconditionally opened `/opt/cvolvepro/CVOLVE-PRO/.streamlit/secrets.toml`. Now it guards
  the import and only opens that path `if os.path.exists(...)`, falling back to env vars —
  mirroring what `api_server.py` already did. (This is why the repo `payment.py` intentionally
  differs from the VPS copy; keep the repo version.)
- **`get_user_session()` crash on jsonb** — it called `json.loads()` on `session_data`, but
  that column is `jsonb`, which psycopg2 already returns as a `dict` → `TypeError`. This broke
  the Phase 2 alignment save/load path. Fixed to pass a `dict`/`list` through and only parse an
  actual string. (Found during end-to-end testing 2026-07-15.)
- **No `.env.example`** — created during recovery; `.env` is built from it.

---

## 8. Quick reference — file map

| File | Role |
|---|---|
| `app.py` | Streamlit UI: login, register, CV generation, **job aggregator tab**, billing, analytics. **Runs `init_db()` at load — needs a live DB to start.** |
| `api_server.py` | FastAPI server for extension / JobsQA / partners |
| `database.py` | PostgreSQL connection, `init_db()` schema bootstrap, CRUD, alignment-answer store |
| `auth.py` | Email auth, session helpers |
| `payment.py` | Stripe checkout / subscriptions (startup fix applied — §7.1) |
| `cv_generator.py` | Résumé parsing, CV / cover letter / interview Q&A, ATS scoring, **CV↔JD gap analysis** |
| `job_aggregator.py` | **Phase 1**: fetch/dedupe/score jobs from Remotive, Arbeitnow, Adzuna |
| `utils.py` | Keyword optimization + `keyword_overlap_score()`, Gemini wrapper, country dial codes |
| `templates.py` | PDF export templates (`professional` only) |
| `styles.css` | Streamlit custom CSS |
| `tests/` | `unittest` suite for the two new features (47 tests) |
| `vps_recovery/cvolvepro_fresh_20260713.sql` | Fresh 182 MB prod dump used for the restore (gitignored) |
| `smtp_test.py` | Standalone SMTP test (not used by the app) |

---

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| App exits immediately with a `psycopg2` / connection error | The DB container is down or `.env` port is wrong. `docker start cvolve-pg`; confirm `.env` has `DB_PORT=5433`. |
| `docker` commands fail / can't reach daemon | Docker Desktop isn't running. `systemctl --user start docker-desktop` (it's a **user** service; this user isn't in the `docker` group). |
| Restore fails with a `\restrict` / syntax error | You're restoring with PostgreSQL < 16 (e.g. the native `:5432` PG14). Use the Docker PG16 container (§4). |
| `password authentication failed` | `.env` password doesn't match the container's `POSTGRES_PASSWORD` (`cvolve_local_2026`). |
| `StreamlitSecretNotFoundError` / secrets error | Missing `.streamlit/secrets.toml` (see §5). It should already exist; recreate if deleted. |
| App starts but CV generation / gap analysis fails | Missing/invalid `GEMINI_API_KEY` (or `OPENAI_API_KEY`) in `.env`. |
| Job search returns nothing from Adzuna | Missing/invalid `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`. Remotive + Arbeitnow still work keyless. |
| Billing tab uses real money | It shouldn't — `.env` uses `sk_test_` keys. If you see `sk_live_`, stop and fix `.env`. |
| No OTP email on register | `RESEND_API_KEY` missing/invalid — expected if unset. |
