"""
job_aggregator.py — Phase 1 Job Aggregator engine (framework-agnostic).

Compliant job search over official/free APIs only (NO scraping), with ZERO LLM calls.
The Streamlit UI (app.py) imports `search_jobs()`; `api_server.py` can reuse it later
without a rewrite. Design & test matrix: docs/JOB_AGGREGATOR_PLAN.md.

Sources:
  Tier A (keyless, always on):  Remotive, Arbeitnow
  Tier B (key-gated):           Adzuna  (ADZUNA_APP_ID + ADZUNA_APP_KEY)
"""
from __future__ import annotations

import os
import re
import copy
import time
import html
import hashlib
import logging
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

import requests

from utils import keyword_overlap_score

logger = logging.getLogger(__name__)

# ----------------------------- Tunables ---------------------------------------
DEFAULT_TIMEOUT = 8            # seconds per source request
MAX_RESULTS_PER_SOURCE = 25
MAX_DESC_CHARS = 8000         # cap description length before scoring (perf)
USER_AGENT = "CVOLVE-PRO-JobAggregator/1.0 (+https://cvolvepro.com)"

# ----------------------------- Work-type labels -------------------------------
REMOTE_IN_COUNTRY = "Remote (in-country)"
REMOTE_WORLDWIDE = "Remote (worldwide)"
REMOTE_UNKNOWN = "Remote — check eligibility"
ONSITE_HYBRID = "Onsite/Hybrid"
CONTRACT = "Contract/Project"
_REMOTE_FAMILY = {REMOTE_IN_COUNTRY, REMOTE_WORLDWIDE, REMOTE_UNKNOWN}

_ADZUNA_CURRENCY = {"gb": "£", "us": "$", "ca": "C$", "au": "A$", "in": "₹",
                    "de": "€", "fr": "€", "nl": "€", "es": "€", "it": "€"}


class SourceAuthError(Exception):
    """Raised when a keyed source rejects our credentials (401/403)."""


# ============================== Data models ===================================
@dataclass
class SearchQuery:
    title: str
    years_experience: Optional[int] = None
    location: str = ""
    geography: str = ""                    # free-text region hint (display/context)
    work_types: list[str] = field(default_factory=list)   # filter; empty = all
    country: str = "gb"                    # Adzuna country code
    limit: int = MAX_RESULTS_PER_SOURCE

    def cache_key(self, source_ids: list[str]) -> str:
        """User-independent key. Excludes work_types (filtered post-cache) and YoE
        (a scoring nudge, not a fetch parameter) so filter tweaks reuse the cache."""
        raw = "|".join([
            self.title.strip().lower(),
            self.location.strip().lower(),
            self.geography.strip().lower(),
            self.country.lower(),
            ",".join(sorted(source_ids)),
        ])
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Job:
    title: str
    company: str
    location: str
    remote_type: str
    job_type: str
    url: str
    source: str
    source_name: str
    posted_date: str = ""
    description: str = ""             # HTML-stripped plain text
    salary: Optional[str] = None
    match_score: Optional[int] = None
    seniority: Optional[str] = None   # inferred level hint (YoE soft signal)
    also_on: list[str] = field(default_factory=list)  # other sources it appeared on

    def dedupe_key(self) -> str:
        u = _normalize_url(self.url)
        if u:
            return "url:" + u
        return "tc:" + self.title.strip().lower() + "|" + self.company.strip().lower()

    def completeness(self) -> int:
        return sum(bool(x) for x in (self.salary, self.posted_date, self.description))


# ============================== Text helpers ==================================
class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data):
        self._parts.append(data)

    def text(self):
        return "".join(self._parts)


def strip_html(raw: str) -> str:
    """Convert source HTML (Remotive etc.) to clean plain text, entity-decoded and
    whitespace-collapsed, capped at MAX_DESC_CHARS. Never let raw HTML reach the
    scorer (pollutes keywords) or the UI (XSS)."""
    if not raw:
        return ""
    try:
        parser = _HTMLStripper()
        parser.feed(raw)
        text = parser.text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_DESC_CHARS]


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    return url.split("?", 1)[0].split("#", 1)[0].rstrip("/").lower()


# ============================== YoE soft signal ===============================
_SENIORITY_PATTERNS = [
    (r"\b(intern|internship)\b", "Intern"),
    (r"\b(junior|jr\.?|entry[- ]level|graduate|associate)\b", "Junior"),
    (r"\b(senior|sr\.?|lead|principal|staff)\b", "Senior"),
    (r"\b(head of|director|\bvp\b|chief|c-level)\b", "Lead+"),
]


def _parse_required_years(text: str) -> Optional[int]:
    """Best-effort 'N+ years' extraction from a JD. Local string parsing only."""
    m = re.search(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yr)\b", text.lower())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def infer_seniority(text: str) -> Optional[str]:
    """Rough level hint for display (never used to hide jobs)."""
    yrs = _parse_required_years(text)
    if yrs is not None:
        if yrs <= 1:
            return "Junior"
        if yrs <= 4:
            return "Mid"
        if yrs <= 7:
            return "Senior"
        return "Senior+"
    low = text.lower()
    for pattern, label in _SENIORITY_PATTERNS:
        if re.search(pattern, low):
            return label
    return None


def _yoe_adjustment(user_years: Optional[int], jd_text: str) -> int:
    """Small bounded nudge (−10..+5) so the match score stays the dominant signal."""
    if user_years is None:
        return 0
    required = _parse_required_years(jd_text)
    if required is None:
        return 0
    gap = required - user_years
    if gap <= 0:
        return 5 if gap >= -3 else 2      # meets/slightly exceeds vs very overqualified
    if gap <= 2:
        return 0
    return -min(10, (gap - 2) * 3)        # job wants notably more experience


# ============================== Source adapters ===============================
class SourceAdapter:
    source = ""
    source_name = ""

    def enabled(self) -> bool:
        return True

    def fetch(self, query: SearchQuery) -> list[dict]:
        raise NotImplementedError

    def normalize(self, raw: dict) -> Optional[Job]:
        raise NotImplementedError

    def _request(self, url, *, params=None, method="GET", json_body=None) -> dict:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        resp = requests.request(method, url, params=params, json=json_body,
                                headers=headers, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()


class RemotiveAdapter(SourceAdapter):
    source = "remotive"
    source_name = "Remotive"
    BASE = "https://remotive.com/api/remote-jobs"

    def fetch(self, query):
        data = self._request(self.BASE, params={"search": query.title, "limit": query.limit})
        return (data.get("jobs") or [])[: query.limit]

    def normalize(self, raw):
        title = (raw.get("title") or "").strip()
        if not title:
            return None
        cand = (raw.get("candidate_required_location") or "").strip()
        remote_type = REMOTE_UNKNOWN
        if cand.lower() in ("worldwide", "anywhere"):
            remote_type = REMOTE_WORLDWIDE
        job_type = (raw.get("job_type") or "").replace("_", " ").strip() or "—"
        return Job(
            title=title,
            company=(raw.get("company_name") or "").strip(),
            location=cand or "Remote",
            remote_type=remote_type,
            job_type=job_type,
            url=raw.get("url") or "",
            source=self.source, source_name=self.source_name,
            posted_date=(raw.get("publication_date") or "")[:10],
            description=strip_html(raw.get("description") or ""),
            salary=(raw.get("salary") or None),
        )


class ArbeitnowAdapter(SourceAdapter):
    source = "arbeitnow"
    source_name = "Arbeitnow"
    BASE = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self, query):
        # Arbeitnow has no server-side search param → filter client-side by title/tags.
        data = self._request(self.BASE)
        jobs = data.get("data") or []
        q = query.title.lower().strip()
        if q:
            def hay(j):
                return (j.get("title", "") + " " + " ".join(j.get("tags", []) or [])).lower()
            jobs = [j for j in jobs if q in hay(j)]
        return jobs[: query.limit]

    def normalize(self, raw):
        title = (raw.get("title") or "").strip()
        if not title:
            return None
        is_remote = bool(raw.get("remote"))
        job_types = raw.get("job_types") or []
        is_contract = any(t.lower() in ("contract", "freelance") for t in job_types)
        if is_remote:
            remote_type = REMOTE_UNKNOWN
        elif is_contract:
            remote_type = CONTRACT
        else:
            remote_type = ONSITE_HYBRID
        created = raw.get("created_at")
        if isinstance(created, (int, float)):
            posted = time.strftime("%Y-%m-%d", time.gmtime(created))
        else:
            posted = (created or "")[:10]
        return Job(
            title=title,
            company=(raw.get("company_name") or "").strip(),
            location=(raw.get("location") or "").strip() or ("Remote" if is_remote else "—"),
            remote_type=remote_type,
            job_type=", ".join(job_types) if job_types else "—",
            url=raw.get("url") or "",
            source=self.source, source_name=self.source_name,
            posted_date=posted,
            description=strip_html(raw.get("description") or ""),
        )


class AdzunaAdapter(SourceAdapter):
    source = "adzuna"
    source_name = "Adzuna"
    BASE = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self):
        self.app_id = os.getenv("ADZUNA_APP_ID")
        self.app_key = os.getenv("ADZUNA_APP_KEY")
        self._currency = ""

    def enabled(self):
        return bool(self.app_id and self.app_key)

    def fetch(self, query):
        country = (query.country or "gb").lower()
        self._currency = _ADZUNA_CURRENCY.get(country, "")
        params = {
            "app_id": self.app_id, "app_key": self.app_key,
            "results_per_page": query.limit,
            "what": query.title,
            "content-type": "application/json",
        }
        if query.location:
            params["where"] = query.location
        url = f"{self.BASE}/{country}/search/1"
        try:
            data = self._request(url, params=params)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            if code in (401, 403):
                raise SourceAuthError(f"Adzuna auth failed ({code}) — check API key") from e
            raise
        return (data.get("results") or [])[: query.limit]

    def _fmt_salary(self, smin, smax):
        cur = self._currency
        try:
            smin = int(smin) if smin else 0
            smax = int(smax) if smax else 0
        except (TypeError, ValueError):
            return None
        if smin and smax and smin != smax:
            return f"{cur}{smin:,}–{cur}{smax:,}"
        if smin:
            return f"{cur}{smin:,}+"
        if smax:
            return f"up to {cur}{smax:,}"
        return None

    def normalize(self, raw):
        title = (raw.get("title") or "").strip()
        if not title:
            return None
        location = ((raw.get("location") or {}).get("display_name") or "").strip()
        contract_time = (raw.get("contract_time") or "")   # full_time / part_time
        contract_type = (raw.get("contract_type") or "")   # permanent / contract
        job_type = " ".join(x.replace("_", " ") for x in (contract_time, contract_type) if x).strip() or "—"
        if "remote" in (title + " " + location).lower():
            remote_type = REMOTE_UNKNOWN
        elif "contract" in contract_type.lower():
            remote_type = CONTRACT
        else:
            remote_type = ONSITE_HYBRID
        return Job(
            title=title,
            company=((raw.get("company") or {}).get("display_name") or "").strip(),
            location=location or "—",
            remote_type=remote_type,
            job_type=job_type,
            url=raw.get("redirect_url") or "",
            source=self.source, source_name=self.source_name,
            posted_date=(raw.get("created") or "")[:10],
            description=strip_html(raw.get("description") or ""),
            salary=self._fmt_salary(raw.get("salary_min"), raw.get("salary_max")),
        )


def default_adapters() -> list[SourceAdapter]:
    return [RemotiveAdapter(), ArbeitnowAdapter(), AdzunaAdapter()]


# ============================== Caching =======================================
# Module-level, user-independent cache: holds normalized jobs WITHOUT match scores.
_CACHE: dict[str, tuple[float, list[Job]]] = {}


def _cache_ttl_seconds() -> int:
    try:
        return int(float(os.getenv("JOB_CACHE_TTL_MIN", "30")) * 60)
    except (TypeError, ValueError):
        return 1800


def clear_cache() -> None:
    _CACHE.clear()


# ============================== Orchestration =================================
def _dedupe(jobs: list[Job]) -> list[Job]:
    kept: dict[str, Job] = {}
    for job in jobs:
        key = job.dedupe_key()
        existing = kept.get(key)
        if existing is None:
            kept[key] = job
        else:
            if job.source_name not in existing.also_on and job.source != existing.source:
                existing.also_on.append(job.source_name)
            # keep the more complete record; carry the "also_on" list forward
            if job.completeness() > existing.completeness():
                job.also_on = existing.also_on
                if existing.source != job.source and existing.source_name not in job.also_on:
                    job.also_on.append(existing.source_name)
                kept[key] = job
    return list(kept.values())


def _matches_work_type(job: Job, wanted: set[str]) -> bool:
    if job.remote_type in wanted:
        return True
    # "Remote — check eligibility" satisfies any remote request (honest inclusion)
    if job.remote_type == REMOTE_UNKNOWN and (wanted & _REMOTE_FAMILY):
        return True
    return False


def search_jobs(query: SearchQuery, resume_text: Optional[str] = None,
                sources: Optional[list[SourceAdapter]] = None) -> dict:
    """Fan out to enabled sources, dedupe, score (per-user), filter, sort.

    Returns:
        {
          "jobs":   list[Job] (filtered + sorted),
          "status": {source_id: "ok"|"cached"|"stale"|"error"|"auth"},
          "counts": {"total": int, "shown": int},
          "empty_reason": None | "no_sources" | "unreachable" | "no_results" | "filtered_out",
        }
    """
    adapters = [a for a in (sources or default_adapters()) if a.enabled()]
    ttl = _cache_ttl_seconds()
    now = time.time()

    collected: list[Job] = []
    status: dict[str, str] = {}

    for adapter in adapters:
        ckey = f"{adapter.source}:{query.cache_key([adapter.source])}"
        cached = _CACHE.get(ckey)
        if cached and (now - cached[0]) < ttl:
            # Work on copies — dedupe/scoring must never mutate the cached (shared) copy.
            collected.extend(copy.deepcopy(cached[1]))
            status[adapter.source] = "cached"
            continue
        try:
            raw_items = adapter.fetch(query)
            jobs: list[Job] = []
            for raw in raw_items:
                try:
                    job = adapter.normalize(raw)
                except Exception:
                    logger.exception("normalize failed for %s", adapter.source)
                    continue
                if job and job.title:
                    jobs.append(job)
            _CACHE[ckey] = (now, jobs)                 # pristine, unscored
            collected.extend(copy.deepcopy(jobs))      # per-request working copies
            status[adapter.source] = "ok"
        except SourceAuthError as e:
            status[adapter.source] = "auth"
            logger.warning("%s", e)
        except Exception as e:
            # stale-while-error: serve last good payload even past TTL
            if cached:
                collected.extend(copy.deepcopy(cached[1]))
                status[adapter.source] = "stale"
            else:
                status[adapter.source] = "error"
            logger.warning("fetch failed for %s: %s", adapter.source, e)

    deduped = _dedupe(collected)

    # Per-request, user-specific scoring (never cached — no cross-user leakage).
    for job in deduped:
        if resume_text and job.description:
            base = keyword_overlap_score(resume_text, job.description)
            base += _yoe_adjustment(query.years_experience, job.description)
            job.match_score = max(0, min(100, base))
        job.seniority = infer_seniority(f"{job.title} {job.description}")

    if query.work_types:
        wanted = set(query.work_types)
        filtered = [j for j in deduped if _matches_work_type(j, wanted)]
    else:
        filtered = list(deduped)

    filtered.sort(
        key=lambda j: (j.match_score if j.match_score is not None else -1, j.posted_date),
        reverse=True,
    )

    # Distinguish the three empty states so the UI can guide the user.
    empty_reason = None
    if not adapters:
        empty_reason = "no_sources"
    elif not filtered:
        reachable = any(s in ("ok", "cached", "stale") for s in status.values())
        if not reachable:
            empty_reason = "unreachable"
        elif deduped:
            empty_reason = "filtered_out"
        else:
            empty_reason = "no_results"

    return {
        "jobs": filtered,
        "status": status,
        "counts": {"total": len(deduped), "shown": len(filtered)},
        "empty_reason": empty_reason,
    }


# ============================== HTML Scraper ===================================
class JobDescriptionHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_blocks: list[str] = []
        self.ignore_tags = {"script", "style", "head", "title", "meta", "link", "noscript", "header", "footer", "nav"}
        self.current_tag_stack: list[str] = []
        self.should_ignore = False

    def handle_starttag(self, tag, attrs):
        self.current_tag_stack.append(tag)
        if tag in self.ignore_tags:
            self.should_ignore = True

    def handle_endtag(self, tag):
        if self.current_tag_stack:
            self.current_tag_stack.pop()
        self.should_ignore = any(t in self.ignore_tags for t in self.current_tag_stack)

    def handle_data(self, data):
        if not self.should_ignore:
            stripped = data.strip()
            if stripped:
                self.text_blocks.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self.text_blocks)


def fetch_full_job_description(url: str) -> Optional[str]:
    """Fetch the original job posting URL and extract readable text from it.
    Returns None if fetching fails or if extracted text is too short.
    """
    if not url:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        if resp.status_code != 200:
            return None
        
        parser = JobDescriptionHTMLParser()
        parser.feed(resp.text)
        text = parser.get_text()
        
        # Clean up excessive newlines and whitespace
        text = re.sub(r'\n+', '\n', text)
        text = re.sub(r' +', ' ', text)
        
        final_text = text.strip()[:MAX_DESC_CHARS]
        if len(final_text) > 200:
            return final_text
    except Exception as e:
        logger.warning("Failed to fetch full job description from %s: %s", url, e)
    return None

