# System Architecture & Operations Guide

Ops-focused companion to [`ARCHITECTURE.md`](ARCHITECTURE.md) (which covers the code
structure). This doc covers **how the whole system runs in production, how you develop
against it, and how you operate the VPS** — written for someone who has never used this
VPS before.

---

## 1. Full-stack picture

```
                        Internet
                           │
              DNS: cvolvepro.com → VPS_IP
                           │
        ┌──────────────────▼──────────────────┐
        │        Hostinger VPS (Ubuntu)        │
        │                                      │
        │   ┌──────────────────────────────┐   │
        │   │  nginx  (:80 / :443 + SSL)   │   │  ← certbot/Let's Encrypt
        │   │  reverse proxy + static      │   │  ← serves index.html (Stripe
        │   └───────┬──────────────┬───────┘   │     "success hop" page)
        │           │              │           │
        │   proxy → :8501   proxy → :8000      │
        │   ┌───────▼──────┐ ┌─────▼────────┐  │
        │   │  Streamlit   │ │   Uvicorn    │  │  ← run as systemd services
        │   │  (app.py)    │ │(api_server.py)│ │     (names: see recon in
        │   └───────┬──────┘ └─────┬────────┘  │      VPS_RECOVERY.md §2.2)
        │           │              │           │
        │           └──────┬───────┘           │
        │                  ▼                   │
        │   deploy root: /opt/cvolvepro/CVOLVE-PRO/
        │   secrets:     .streamlit/secrets.toml
        └──────────────────┬───────────────────┘
                           │
                ┌──────────▼──────────┐
                │  PostgreSQL          │  ← on-VPS or Hostinger-managed
                │  db: cvolvepro       │     (confirm via recon §2.4)
                └─────────────────────┘

External clients & services:
  • Chrome extension (id fbcioogb…) ──► api_server /api/*        (CORS-allowed)
  • jobsqa.com frontend            ──► api_server /api/jobsqa/*  (CORS-allowed)
  • Stripe  ◄── checkout redirects; ──► webhooks → /api/jobsqa/webhook
  • Google Gemini / OpenAI  ◄── cv_generator.py, utils.py
  • Resend  ◄── registration OTP emails
```

Key facts:

- **Two Python processes**, one codebase: Streamlit UI on `:8501`, FastAPI on `:8000`.
  nginx terminates SSL and routes to both.
- **Secrets in production** live in `/opt/cvolvepro/CVOLVE-PRO/.streamlit/secrets.toml`
  (loaded by `payment.py`, `api_server.py`, and `st.secrets`). Locally we use `.env` instead.
- **Stripe flow**: user → Stripe Checkout → redirect back (via the nginx-served
  `index.html` hop page → Streamlit success handler) and/or webhook → credits added.
  Payment idempotency via the `payments` table.

---

## 2. Development workflow (local ↔ VPS)

**Never edit code directly on the VPS.** The workflow to establish:

```
┌──────────────┐   git push    ┌──────────────┐   deploy      ┌──────────────┐
│ Local dev     │ ────────────► │ Private repo │ ────────────► │  VPS          │
│ (this repo,   │               │ (GitHub)     │  ssh + pull/  │ /opt/cvolvepro│
│ local PG copy)│               │              │  rsync        │  + restart    │
└──────────────┘               └──────────────┘               └──────────────┘
```

1. **Local**: develop and test against your local Postgres (restored from a dump). Never
   point local dev at the production DB.
2. **Version control**: push this repo to a **private** GitHub repo (client gave no repo —
   you become the source of truth; do this before any feature work).
3. **Deploy** (after VPS recovery confirms how services run), the standard cycle is:

```bash
# from local machine
ssh cvolve-vps
cd /opt/cvolvepro/CVOLVE-PRO
sudo systemctl stop <streamlit-service> <api-service>   # names from recon
git pull            # once the VPS is converted to a git checkout (recommended)
# OR, until then:   rsync -avz --exclude '.venv' --exclude '.env' --exclude '.streamlit' ./ cvolve-vps:/opt/cvolvepro/CVOLVE-PRO/
pip install -r requirements.txt                          # if deps changed
sudo systemctl start <streamlit-service> <api-service>
```

4. **Rollback** = `git checkout <previous-tag>` + restart. Tag every deploy
   (`git tag deploy-YYYYMMDD`).

> First deploys: do them at low-traffic hours, verify `https://cvolvepro.com` and
> `GET /health` immediately after restart.

---

## 3. Operational runbook

### 3.1 Service control (names TBD from recon)

```bash
sudo systemctl status  <service>
sudo systemctl restart <service>
journalctl -u <service> -f            # live logs
journalctl -u <service> --since today
```

### 3.2 Log locations

| What | Where |
|---|---|
| App services | `journalctl -u <service>` |
| nginx access/errors | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |
| Postgres (if on VPS) | `/var/log/postgresql/` |

### 3.3 Backups (set up immediately if none exist)

The DB is the only irreplaceable asset (user accounts, credits, payments). Minimum viable:

```bash
# on the VPS: /usr/local/bin/backup_cvolvepro.sh
#!/bin/bash
set -e
pg_dump -U postgres cvolvepro | gzip > /var/backups/cvolvepro_$(date +%F).sql.gz
find /var/backups -name 'cvolvepro_*.sql.gz' -mtime +14 -delete
```

```bash
# nightly at 03:15
sudo crontab -e
15 3 * * * /usr/local/bin/backup_cvolvepro.sh
```

Plus: periodically pull a copy **off the VPS** (`rsync cvolve-vps:/var/backups/ ...`) — a
backup that only lives on the same server is not a backup.

### 3.4 SSL

- Certs are (almost certainly) Let's Encrypt via certbot: `sudo certbot certificates`.
- Renewal is normally automatic (`systemctl list-timers | grep certbot`). Verify it.

### 3.5 Health checks

```bash
curl -s https://cvolvepro.com -o /dev/null -w '%{http_code}\n'   # expect 200
curl -s https://<api-host>/health                                 # FastAPI health
curl -s https://<api-host>/api/jobsqa/health                      # JobsQA health
```

Consider a free uptime monitor (UptimeRobot etc.) pointed at both once you own operations.

---

## 4. Environments summary

| | Local dev | Production (VPS) |
|---|---|---|
| Code | this repo | `/opt/cvolvepro/CVOLVE-PRO/` |
| Config | `.env` (from `.env.example`) | `.streamlit/secrets.toml` |
| Python | `.venv` (Python 3.11) | check on VPS (recon) |
| DB | local Postgres 14, `cvolvepro` (restored dump) | prod Postgres (on-VPS or Hostinger-managed) |
| Web entry | `streamlit run app.py` → :8501 | nginx → :8501 / :8000 |
| Stripe | test keys (recommended) | live keys |

> Get **Stripe test-mode keys** for local dev so you can exercise checkout without real
> charges; keep the live keys only in production.

---

## 5. Things you'll eventually need (beyond code)

Access/assets to collect from the client — most feature and security work will hit these:

- [ ] **Stripe dashboard access** — webhook configuration, live/test keys, product/price IDs
- [ ] **Domain/DNS control** (where cvolvepro.com is registered) — needed for any subdomain, email (SPF/DKIM for Resend), or host migration
- [ ] **Resend account** — domain verification status, sending limits
- [ ] **Google AI Studio / Gemini billing** — quota and cost visibility (client is API-cost sensitive; you'll want usage dashboards)
- [ ] **OpenAI account** — same
- [ ] **Chrome Web Store developer account** + extension source — extension updates are impossible without both
- [ ] **Hostinger panel access** — VPS resizing, snapshots (check if VPS snapshots are enabled — cheap disaster recovery)
- [ ] Written authorization for the **security review/hardening work** (it's their explicit request in Feature_list.txt — keep that email/document)
- [ ] **Privacy/data answers**: CVs and interview answers are personal data. Confirm with the client what retention/deletion policy they want (and check the site has a privacy policy) before adding features that store more user content (transcripts, recordings later).
