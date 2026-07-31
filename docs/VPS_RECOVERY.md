# VPS Recovery Guide — Hostinger

Step-by-step guide for the **first SSH session** into the client's Hostinger VPS, and for
recovering every file this repo is missing. The full list of what's missing and why is in
[MISSING_FILES_AUDIT.md](MISSING_FILES_AUDIT.md).

> ⚠️ **This is a LIVE production server with real users, payments, and data.**
> Follow the safety rules below. Everything in Phase A is read-only.

---

## 0. Safety rules

1. **Read-only first.** In your first sessions, only `ls`, `cat`, `cp`, `rsync` — never
   `rm`, `mv`, or edits, and **do not restart services**.
2. **Never run `pg_dump`/heavy copies at peak hours** if you can avoid it (a 182 MB+ dump
   causes some IO load; fine off-peak).
3. **Everything you recover containing credentials stays out of git.** The repo's
   `.gitignore` already excludes `.env`, `secrets.toml`, and `vps_recovery/`.
4. Keep a log of every command you run on the VPS (copy-paste into a scratch note) — you're
   reverse-engineering someone else's deployment; the log will save you later.

---

## 1. Connect

```bash
# Basic connection (Hostinger usually gives root or a sudo user + IP)
ssh USER@VPS_IP
# If they gave a non-standard port:
ssh -p PORT USER@VPS_IP
```

Recommended: set up an SSH config entry on your machine so every later command is short:

```
# ~/.ssh/config
Host cvolve-vps
    HostName VPS_IP
    User USER
    Port 22
```

Then it's just `ssh cvolve-vps`, and `rsync`/`scp` can use `cvolve-vps:` as the remote.

> Better than passwords: `ssh-copy-id cvolve-vps` to install your public key, then consider
> disabling password auth later (Phase 1 security work, not now).

---

## 2. Phase A — Recon (read-only)

Run these and save the output. Goal: understand **how the app actually runs** before touching anything.

### 2.1 The deploy directory

```bash
ls -la /opt/cvolvepro/CVOLVE-PRO/
ls -la /opt/cvolvepro/CVOLVE-PRO/.streamlit/
# Any other copies/projects on the box?
ls -la /opt/ /srv/ /var/www/ 2>/dev/null
```

### 2.2 How the processes run

```bash
ps aux | grep -E 'streamlit|uvicorn|gunicorn|python' | grep -v grep
systemctl list-units --type=service | grep -iE 'cvolve|streamlit|uvicorn|jobsqa'
ls /etc/systemd/system/*.service 2>/dev/null
# If nothing in systemd, check for other process managers:
which pm2 supervisorctl 2>/dev/null; ls /etc/supervisor/conf.d/ 2>/dev/null
crontab -l; sudo ls /var/spool/cron/crontabs/ 2>/dev/null
```

### 2.3 Web server + SSL

```bash
ls /etc/nginx/sites-enabled/
cat /etc/nginx/sites-enabled/*
sudo certbot certificates 2>/dev/null   # SSL cert status + renewal
```

### 2.4 Database

```bash
# Is Postgres local on the VPS or a separate Hostinger DB host?
grep -rE "DB_HOST|host" /opt/cvolvepro/CVOLVE-PRO/.env /opt/cvolvepro/CVOLVE-PRO/.streamlit/secrets.toml 2>/dev/null
systemctl status postgresql 2>/dev/null | head -5
```

### 2.5 Logs (know where to look when things break)

```bash
ls /var/log/nginx/
journalctl -u <the-service-name-you-found> --since "1 hour ago" | tail -50
```

---

## 3. Phase B — Pull everything to your machine

From **your local machine** (not on the VPS). Files land in `vps_recovery/` (gitignored).

```bash
mkdir -p vps_recovery

# 1. The entire deploy directory — code, secrets, .streamlit, everything
rsync -avz cvolve-vps:/opt/cvolvepro/CVOLVE-PRO/ vps_recovery/CVOLVE-PRO/

# 2. Nginx configs
rsync -avz cvolve-vps:/etc/nginx/sites-available/ vps_recovery/nginx/sites-available/
rsync -avz cvolve-vps:/etc/nginx/sites-enabled/  vps_recovery/nginx/sites-enabled/

# 3. systemd units (adjust names to what you found in recon)
rsync -avz cvolve-vps:/etc/systemd/system/ vps_recovery/systemd/ --include='*.service' --include='*/' --exclude='*'

# 4. Anything a web root serves (index.html "success hop" page lives somewhere here)
rsync -avz cvolve-vps:/var/www/ vps_recovery/www/ 2>/dev/null
```

### 3.1 Fresh database dump (the repo's cvolvepro.sql may be stale)

If Postgres runs **on the VPS**:

```bash
ssh cvolve-vps "pg_dump -U postgres -d cvolvepro" > vps_recovery/cvolvepro_fresh_$(date +%Y%m%d).sql
```

If it's a **separate Hostinger-managed Postgres** (check DB_HOST from recon), dump from
your machine using the DB credentials the client gave:

```bash
pg_dump -h DB_HOST -p DB_PORT -U DB_USER -d cvolvepro > vps_recovery/cvolvepro_fresh_$(date +%Y%m%d).sql
```

---

## 4. Phase C — Compare VPS code against this repo

The VPS may have **newer code** than what was recovered into this repo. Find the drift:

```bash
# Quick: which files differ or exist only on one side
diff -rq vps_recovery/CVOLVE-PRO/ . \
  --exclude='.venv' --exclude='.git' --exclude='vps_recovery' \
  --exclude='__pycache__' --exclude='*.sql' --exclude='users.db'

# Then inspect each differing file:
diff vps_recovery/CVOLVE-PRO/app.py app.py | head -50
```

**Rule: the VPS is the source of truth for code content** (it's what's actually running).
If a file differs, take the VPS version — except `payment.py`, where you must re-apply the
local-compat patch (see [LOCAL_SETUP.md §3.1](LOCAL_SETUP.md)) if the VPS copy still has the
hardcoded `open()`.

---

## 5. Phase D — Wire recovered secrets into local `.env`

Open `vps_recovery/CVOLVE-PRO/.streamlit/secrets.toml` (and any `.env` you found) and copy
values into your local `.env` (created from `.env.example`):

| From secrets.toml / VPS .env | Into local .env |
|---|---|
| `STRIPE_SECRET_KEY` | `STRIPE_SECRET_KEY` |
| `STRIPE_PUBLIC_KEY` | `STRIPE_PUBLIC_KEY` |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `GEMINI_API_KEY` |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` |
| `RESEND_API_KEY` | `RESEND_API_KEY` |
| `JWT_SECRET` | `JWT_SECRET` |
| DB credentials | `DB_*` — **keep local DB values for local dev**; note the prod values separately |

> ⚠️ For local dev, point `DB_*` at your **local** Postgres, not the production DB. Never
> develop against the live database.

Optionally also copy the whole file to `.streamlit/secrets.toml` locally — `app.py:1809`
reads `st.secrets.get("BASE_URL", ...)`; set `BASE_URL = "http://localhost:8501"` locally.

---

## 6. Recovery checklist

Tick these off (they mirror [MISSING_FILES_AUDIT.md](MISSING_FILES_AUDIT.md)):

> **Progress 2026-07-13:** Phase A recon done directly on the box (results in
> `docs/Vps recvoery results.pdf`, gitignored). Phase B pull was attempted but failed —
> the `rsync`/`pg_dump` commands were run *on the VPS* instead of locally. Use
> `scripts/vps_pull.sh` (run from your laptop) to do Phase B correctly.

- [x] SSH access works (`root@31.97.231.239`) — ⏳ `~/.ssh/config` alias optional (script uses IP)
- [x] Recon output saved (processes, systemd, nginx, cron, logs, certs)
- [x] `/opt/cvolvepro/CVOLVE-PRO/` pulled into `vps_recovery/` (`scripts/vps_pull.sh`, 2026-07-13)
- [x] `.streamlit/secrets.toml` + `.env` recovered to `vps_recovery/CVOLVE-PRO/` — ⏳ copy into local `.env`
- [x] nginx configs pulled (`vps_recovery/nginx/sites-available/`, 12 files)
- [x] systemd units pulled (`vps_recovery/systemd/`: `cvolvepro.service`, `cvolvepro_api.service`)
- [x] Stripe success page recovered — `payment-success.html` in
      `vps_recovery/frontend-interview/` (**not** `index.html`)
- [x] Fresh `pg_dump` taken — `vps_recovery/cvolvepro_fresh_20260713.sql` (182 MiB, clean).
      ⏳ **still to restore locally** — restore this fresh dump, not the stale bundled
      `cvolvepro.sql`. Steps in [LOCAL_SETUP.md §4](LOCAL_SETUP.md)
- [x] `diff -rq` drift check done — **production code is byte-identical to the repo** except
      `payment.py` (repo keeps the local-compat patch) and `requirements.txt` (repo is the
      complete/pinned version; the VPS copy is missing fastapi/uvicorn/PyJWT/werkzeug). No
      code needs pulling back into the repo.
- [x] Chrome extension source — **found on VPS** (`/opt/cvolvepro/cvolvepro-extension/`);
      only the client's Chrome Web Store account is still needed
- [ ] **⚠️ Backup situation: NONE today** — `crontab -l` = `no crontab for root`. Set up a
      nightly `pg_dump` cron ASAP (Phase 1); see [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
