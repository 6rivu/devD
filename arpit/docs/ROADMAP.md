# CVOLVE PRO — Phased Roadmap

Maps the client's requests ([`Feature_list.txt`](Feature_list.txt)) to a
phased, **bare-minimum, API-cost-conscious** delivery plan. The client explicitly asked for
phases, priorities, and what's needed from them — this doc doubles as the basis for that
proposal.

**Guiding constraints (agreed):**
- Client is sensitive to API usage/cost → minimize LLM calls per user action, prefer local
  computation, batch prompts.
- Bare-minimum first versions; polish later.
- Voice features (record → transcribe) are the biggest new per-use API cost → **deferred to
  their own phase** the client can approve separately.

---

## Phase 0 — Recovery & baseline *(prerequisite for everything)*

**Goal:** own the system: full source, secrets, fresh data, version control, backups.

| Item | Detail |
|---|---|
| VPS recovery | Follow [VPS_RECOVERY.md](VPS_RECOVERY.md): pull deploy dir, secrets, nginx/systemd configs, `index.html`; diff against repo; take fresh `pg_dump` |
| Local dev running | [LOCAL_SETUP.md](LOCAL_SETUP.md): venv ✅, deps ✅, `payment.py` patch ✅, DB restore, `.env` |
| Version control | Push to **private GitHub repo**; convert VPS to a git checkout for clean deploys |
| Backups | Nightly `pg_dump` cron on VPS + off-server copy ([SYSTEM_ARCHITECTURE.md §3.3](SYSTEM_ARCHITECTURE.md)) |
| Stripe test keys | For safe local checkout testing |

**API cost impact:** none. **New deps:** none.
**Needed from client:** nothing beyond what's already given (VPS + DB creds). Chrome
extension source + accounts list can be requested in parallel (see SYSTEM_ARCHITECTURE §5).

---

## Phase 5 — API security review & hardening *(client priority #1)*

**Goal (client's words):** "users should not be able to attack, inspect, misuse, or bypass
the platform's APIs or credits."

Bare-minimum hardening set, all in `api_server.py` + nginx unless noted:

| Area | Action |
|---|---|
| Rate limiting | Add `slowapi` per-IP + per-user limits on login, signup, OTP, and all generation endpoints (OTP endpoints are the classic abuse target) |
| Kill debug surface | Remove/gate `/api/debug/preview_cv`; disable `/docs`, `/redoc`, `/openapi.json` in production (`FastAPI(docs_url=None, ...)`) |
| JWT audit | Enforce expiry on all tokens; verify `JWT_SECRET` is strong + not defaulted; scope check (`app=jobsqa`) on every JobsQA route |
| Credit enforcement audit | Verify every credit deduction happens **server-side, atomically, before returning output**; check for TOCTOU/negative-balance paths; make Stripe webhook credit top-ups idempotent (`payments` table) |
| Input validation | Size caps + type checks on `resume_base64` (reject >~5 MB, non-PDF/DOCX); length caps on job descriptions (LLM cost control doubles as abuse control) |
| CORS | Tighten allowlist; no wildcard; verify allowed methods/headers minimal |
| Auth hygiene | Uniform error messages (no user-enumeration via login/signup responses); OTP attempt limits + expiry |
| Logging/monitoring | Structured request logging (user, endpoint, credits delta); log auth failures; simple alert on anomaly (e.g., fail2ban on nginx + auth log) |
| Transport | HTTPS-only + HSTS at nginx; secure headers (X-Content-Type-Options, X-Frame-Options) |
| Secrets | Rotate any keys that were shared over insecure channels during handover |

**API cost impact:** none (actually reduces waste from abuse).
**New deps:** `slowapi`.
**Needed from client:** written authorization for security work (they've requested it in
Feature_list.txt — keep that record); Stripe dashboard access to verify webhook config.

---

## Phase 3 — Interview practice module v1

**Goal:** turn the existing Q&A generator into a practice session with evaluation — the
client's main USP. Builds on `generate_interview_qa` in `cv_generator.py` and
`export_interview_qa`.

Feature mapping (client ask → v1 scope):

| Client ask | v1 implementation |
|---|---|
| Behavioral + Technical sections | One structured Gemini call returns both sections, JSON-tagged |
| Difficulty: Simple / Hard / Very hard | Same single call — questions tagged by difficulty |
| Duration 15/30/45 min | Selector drives question count (e.g., 5/10/15) |
| Credit by duration | Tiered deduction (e.g., 2/3/5 credits) via existing `record_credit_usage` |
| Download Word + PDF | Extend existing export (reportlab + python-docx already in requirements) |
| AI interviewer asks one by one | Streamlit sequential flow: one question per step, session-state driven |
| Answer by typing | ✅ v1 |
| Answer by speaking | ❌ deferred → Phase 5 |
| AI evaluates answers (meaning, keywords, structure…) | **Single batched Gemini call at session end** evaluates all answers at once |
| Full feedback report (strengths, gaps, keywords covered/missed, per-section scores, suggestions) | Output of that same evaluation call, rendered + downloadable |

**API cost impact:** ~**2 Gemini calls per full session** (generate + evaluate), regardless
of question count. **New deps:** none.
**DB:** new table for practice sessions/answers (design at implementation time).
**Needed from client:** sign-off on credit pricing tiers.

---

## Phase 2 — CV ↔ job-description alignment flow

**Goal:** stop the generator from inventing unsupported experience; ask the user targeted
questions when the CV lacks evidence for the JD.

| Client ask | v1 implementation |
|---|---|
| Compare CV vs JD | One Gemini "gap analysis" call → JSON: `sufficient: bool`, list of gaps |
| Enough evidence → generate directly | If `sufficient`, existing flow unchanged (no extra call cost) |
| Not enough → follow-up questions | Streamlit form: one clear question per gap, **with an example answer** under each |
| Typed answer space | ✅ v1 (text areas) |
| Spoken answers | ❌ deferred → Phase 5 |
| Answers improve CV, cover letter, interview prep | Answers appended to generation context (stored in `user_sessions`) |
| Avoid inventing experience | Hard instruction added to all generation prompts |
| Mandatory disclaimer | Client's exact disclaimer text shown before generation (verbatim from Feature_list.txt:130) |

**API cost impact:** **+1 Gemini call max** per generation (the gap analysis), and only its
results gate whether questions appear. **New deps:** none.

---

## Phase 1 — Job aggregator v1

**Goal:** compliant job search — client explicitly forbids illegal scraping.

| Aspect | v1 implementation |
|---|---|
| Sources | **Official/free APIs and feeds only**: Remotive (API), Arbeitnow (API), Adzuna (free-tier API key), Jooble (free API key). No scraping anywhere. |
| Search form | Job title, years of experience, location, work type, geography |
| Work-type filters | Remote-in-country / Worldwide-remote / Contract-project / Onsite-hybrid — mapped from each source's fields; where a source can't distinguish visa-bound vs worldwide remote, label honestly ("Remote — check eligibility") |
| Job card fields | Title, company, location, remote type, job type, source link, posted date, match score |
| Match score | **Local keyword overlap** between resume text and job description — reuses the keyword logic in `utils.py`. **Zero LLM calls.** |
| Caching | Cache source responses (per query, ~15–60 min TTL) to respect provider rate limits and speed up the UI |
| Credits | 1 credit per search (existing `credit_usage` pattern) |

**API cost impact:** zero LLM calls; only free-tier job-board APIs.
**New deps:** `requests` (likely already transitively present; pin it).
**Needed from client:** none technically; agreement on which sources are "good enough" for v1.

---

## Phase 4 — Deferred: voice & AI interviewer *(separate approval)*

Held back deliberately — it's the one area with unavoidable **per-use API cost**:

- Mic recording in Streamlit (component, e.g. `streamlit-mic-recorder`)
- Transcription per answer (Gemini audio input or Whisper) — cost scales with usage
- Optionally: AI interviewer voice output (TTS) — further cost
- Applies to both the interview module (Phase 2) and alignment flow (Phase 3) answers

**Present to the client with per-session cost estimates** once Phases 2–3 usage data exists,
so they can decide with real numbers.

---

I have rearranged the phase no according to the need not according to the suggested because they are more of feature focused rather than quality or security or smth. So we are targetting about feature first approach wehre we are just pushing featrures in to the app

