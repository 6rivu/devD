# CVOLVE PRO — Project Architecture

CVOLVE PRO is an AI-powered resume/CV optimization platform with two entry points:

1. **Streamlit web app** (`app.py`) — full product UI for individuals and business users
2. **FastAPI REST API** (`api_server.py`) — backend for Chrome extension, JobsQA.com, and third-party integrations

Both share the same core modules: database, auth, payments, CV generation, and templates.

---

## High-level diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                        │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│  Browser (Streamlit) │  jobsqa.com frontend │  Chrome extension             │
│  streamlit run app.py│  (external)          │  (cvolvepro.com)              │
└──────────┬───────────┴──────────┬───────────┴───────────────┬───────────────┘
           │                    │                           │
           v                    v                           v
┌──────────────────┐   ┌─────────────────────────────────────────────────────┐
│     app.py       │   │              api_server.py (FastAPI + uvicorn)       │
│  Streamlit UI    │   │  /api/login  /api/generate_cv  /api/generate_cl      │
│                  │   │  /api/jobsqa/*  (signup, login, interview Q&A, etc.) │
└────────┬─────────┘   └──────────────────────────┬──────────────────────────┘
         │                                        │
         └────────────────┬───────────────────────┘
                          v
         ┌────────────────────────────────────────────────────────────┐
         │                    SHARED CORE MODULES                      │
         ├─────────────┬─────────────┬──────────────┬───────────────────┤
         │  auth.py    │ database.py │  payment.py  │  cv_generator.py  │
         │  (session + │  (Postgres) │  (Stripe)    │  (Gemini/OpenAI)  │
         │   JWT login)│             │              │                   │
         ├─────────────┴─────────────┴──────────────┴───────────────────┤
         │  templates.py (PDF)   utils.py (keywords, Gemini helper)    │
         └────────────────────────────┬───────────────────────────────┘
                                      v
         ┌────────────────────────────────────────────────────────────┐
         │                     EXTERNAL SERVICES                       │
         ├──────────────┬──────────────┬──────────────┬───────────────┤
         │  PostgreSQL  │ Google Gemini│   OpenAI     │    Stripe     │
         │              │  (+ OpenAI   │ (Premium     │  (checkout +  │
         │              │   Classic)   │  Classic)    │   webhooks)   │
         ├──────────────┴──────────────┴──────────────┴───────────────┤
         │                        Resend (email OTP)                    │
         └────────────────────────────────────────────────────────────┘
```

---

## File map

| File | Role |
|------|------|
| `app.py` | Main Streamlit application: login, register, CV generation, billing, analytics |
| `api_server.py` | FastAPI server for programmatic access (extension, JobsQA, partners) |
| `database.py` | PostgreSQL connection, schema init, user/credits/payments CRUD |
| `auth.py` | Email auth, session helpers (Streamlit), mock Google/LinkedIn stubs |
| `payment.py` | Stripe checkout sessions, subscriptions, JobsQA payment handling |
| `cv_generator.py` | Resume parsing, CV/cover letter/interview Q&A generation, ATS scoring |
| `templates.py` | PDF export templates (currently `professional` only) |
| `utils.py` | Keyword optimization, Gemini API wrapper, country dial codes |
| `styles.css` | Streamlit custom CSS (loaded by `app.py`) |
| `smtp_test.py` | Standalone SMTP test script (not used by main app) |

---

## How to run locally

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your DB, API keys, and Stripe credentials
```

### 3. Initialize database

```python
from database import init_db
init_db()
```

Run once after PostgreSQL is up. Creates tables for **CVolve individual + business** users.

> **Note:** JobsQA tables (`jobsqa_users`, `jobsqa_credits`, etc.) are used by `api_server.py` but are **not** created by `init_db()` today. See [JobsQA schema](#jobsqa-database-schema) below if you integrate JobsQA.

### 4. Start Streamlit UI

```bash
streamlit run app.py
```

Default: `http://localhost:8501`

### 5. Start FastAPI (optional, for API integrations)

```bash
python api_server.py
# or: uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Default: `http://localhost:8000`

---

## User flows

### Individual user (Streamlit)

```
Register → OTP email (Resend) → Verify → Login
    → Upload resume + paste JD
    → Generate CV / Cover letter / Interview Q&A / ATS check
    → Credits deducted per feature
    → Billing tab → Stripe checkout → credits/subscription
```

### Business user (Streamlit)

```
Business Portal → Register company → Stripe business plan
    → Shared credit pool → same CV features as individual
```

### API consumer (FastAPI)

```
POST /api/login → JWT token
POST /api/generate_cv  (Authorization: Bearer <token>)
POST /api/generate_cl
```

### JobsQA (separate product on same backend)

```
POST /api/jobsqa/signup → OTP → POST /api/jobsqa/verify-otp
POST /api/jobsqa/login → JobsQA-scoped JWT (app=jobsqa)
POST /api/jobsqa/generate_interview_qa
POST /api/jobsqa/create_checkout → Stripe → webhook credits
```

---

## Credit costs (defaults)

| Feature | Credits |
|---------|---------|
| ATS score check | 1 |
| Job recommendations | 1 |
| Cover letter | 2 |
| CV generation | 3 |
| Interview Q&A | 3 |

Configurable via env: `CV_CREDIT_COST` (API CV default = 3).

---

## API reference (integration points)

Base URL: `http://localhost:8000` (or your deployed host)

### Health

| Method | Path | Auth |
|--------|------|------|
| GET | `/health` | No |
| GET | `/api/jobsqa/health` | No |

### CVolve (Chrome extension / partners)

| Method | Path | Auth | Body |
|--------|------|------|------|
| POST | `/api/login` | No | `{ "email", "password" }` → `{ token, credits }` |
| POST | `/api/generate_cv` | Bearer JWT | See `GenerateCVRequest` below |
| POST | `/api/generate_cl` | Bearer JWT | `{ job_description, resume_base64, resume_filename, language }` |
| POST | `/api/debug/preview_cv` | Bearer JWT | Same as generate_cv (debug) |

**GenerateCVRequest** (JSON):

```json
{
  "job_description": "string (required)",
  "target_match": 90,
  "resume_base64": "base64-encoded PDF or DOCX",
  "resume_filename": "resume.pdf",
  "template": "professional",
  "sections": {
    "Professional Summary": true,
    "Work Experience": true
  },
  "language": "English",
  "model": "gemini",
  "output_format": "pdf"
}
```

### JobsQA

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/jobsqa/signup` | No | `{ email, password }` → sends OTP |
| POST | `/api/jobsqa/verify-otp` | No | `{ email, otp }` |
| POST | `/api/jobsqa/login` | No | Returns JobsQA JWT |
| GET | `/api/jobsqa/me` | Bearer JobsQA JWT | User + credits |
| POST | `/api/jobsqa/generate_interview_qa` | Bearer JobsQA JWT | Resume + JD → Q&A |
| POST | `/api/jobsqa/create_checkout` | Bearer JobsQA JWT | Stripe session |
| POST | `/api/jobsqa/webhook` | Stripe signature | Credit top-up |

CORS allowed origins (in code): `cvolvepro.com`, `jobsqa.com`, Chrome extension ID.

---

## Database schema

### Created by `init_db()`

- `users` — individual accounts, credits, verification
- `subscriptions` — plan name, Stripe ID, dates
- `cv_generations` — history + ATS scores
- `user_sessions` — auto-save JSON (Streamlit)
- `payments` — Stripe payment idempotency
- `discount_codes`, `user_special_discounts`, `user_coupon_usage`
- `credit_usage` — per-feature audit log
- `business_users`, `business_subscriptions`, `business_credit_usage`

### JobsQA database schema

These tables are **required for JobsQA API** but not auto-created by `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS jobsqa_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    email_otp VARCHAR(10),
    otp_created_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobsqa_credits (
    user_id INTEGER PRIMARY KEY REFERENCES jobsqa_users(id),
    credits INTEGER DEFAULT 0,
    expires_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobsqa_credit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES jobsqa_users(id),
    action VARCHAR(100),
    credits_change INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobsqa_interview_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES jobsqa_users(id),
    resume_filename VARCHAR(255),
    job_description TEXT,
    interview_qa TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Environment variables

See `.env.example` for the full list. Critical ones:

| Variable | Used by |
|----------|---------|
| `DB_*` | All modules |
| `GEMINI_API_KEY` | CV generation (default model) |
| `OPENAI_API_KEY` | Premium Classic model |
| `STRIPE_SECRET_KEY` | Payments |
| `RESEND_API_KEY` | Registration OTP |
| `JWT_SECRET` | FastAPI bearer tokens |

Production also supports loading from `.streamlit/secrets.toml` (path hardcoded for Linux deploy: `/opt/cvolvepro/CVOLVE-PRO/.streamlit/secrets.toml`).

---

## Integration guide

### Add a new frontend (React, mobile, etc.)

1. Run `api_server.py` behind HTTPS.
2. Call `POST /api/login` or JobsQA signup/login flow.
3. Store JWT; send `Authorization: Bearer <token>` on protected routes.
4. Encode resume as base64 in JSON (no multipart upload required).

### Add a new AI feature

1. Add function in `cv_generator.py`.
2. Wire Streamlit button in `app.py` (optional).
3. Add FastAPI route in `api_server.py` (optional).
4. Deduct credits via `database.update_user_credits` or `jobsqa_update_credits`.
5. Log usage in `credit_usage` / `jobsqa_credit_logs`.

### Add a new payment product

1. Extend `payment.create_checkout_session` or `create_jobsqa_checkout_session`.
2. Handle success in `app.py` (`handle_stripe_return_globally`) or webhook in `api_server.py`.
3. Persist with `database.save_payment`.

### Add a new CV template

1. Implement renderer in `templates.py` (see `create_professional_template`).
2. Register name in `apply_template()`.
3. Expose in Streamlit sidebar / API `template` field.

---

## Known gaps (useful when integrating)

| Gap | Impact |
|-----|--------|
| JobsQA tables not in `init_db()` | Run SQL above manually |
| `show_interview_qa_page()` not in main tabs | Q&A works from CV tab only in Streamlit |
| Only one PDF template | All template names map to `professional` |
| Google/LinkedIn auth are stubs | Email auth only in production UI |
| No bundled JobsQA frontend | API-only; build your own client |

---

## Deployment sketch

```
                    ┌─────────────┐
   Users ──────────►│   Nginx     │
                    │  (reverse   │
                    │   proxy)    │
                    └──┬──────┬───┘
                       │      │
              :8501    │      │    :8000
                       v      v
                 Streamlit   Uvicorn
                 (app.py)    (api_server.py)
                       \      /
                        v    v
                    PostgreSQL
```

Both processes need the same `.env` and Python dependencies from `requirements.txt`.
