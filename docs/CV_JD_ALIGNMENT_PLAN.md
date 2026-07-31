# CV ↔ JD Alignment Flow — Implementation Plan

Concrete build plan for **Phase 2** of [ROADMAP.md](ROADMAP.md). Goal: stop the generator
from inventing unsupported experience; when the CV lacks evidence for the JD, ask the user
targeted follow-up questions and use their real answers to enrich generation.

**Guiding constraints (from the roadmap):** minimize LLM calls (**+1 Gemini call max** per
generation), bare-minimum v1, **voice answers deferred to Phase 4**.

---

## 0. Critical finding — this phase is TWO jobs, not one

While tracing the flow, the active generation prompt (`prompt_5` in
[cv_generator.py](../cv_generator.py#L478), used for both Gemini and OpenAI paths) was found
to **explicitly instruct fabrication**:

- `cv_generator.py:700` — *"Fabricate work experience to better align with the JD…"*
- `cv_generator.py:727+` — bullet math like *"4 original + 2 fabricated from JD"*
- The same language is duplicated across the dormant `prompt`, `prompt_2`, `prompt_3`,
  `prompt_4` variants, and echoes in the cover-letter prompt.

This is the **direct opposite** of the client's written requirement ("The tool should avoid
inventing unsupported experience") and of the disclaimer they want shown. Therefore Phase 2 =

1. **Prompt remediation** (§7) — remove fabrication instructions, add hard "do not invent"
   guardrails to CV + cover-letter + interview prompts. *This is the higher-priority half:
   it's a live honesty/liability issue in the current product.*
2. **The alignment flow** (§2–§6) — the new gap-analysis → questions → enrichment feature.

> ⚠️ Remediation is a **material product change**: honest generation will likely lower the
> headline ATS scores the tool currently produces. Needs explicit client sign-off (§11).

---

## 1. End-to-end flow

```
Upload CV + paste JD
        │
   [Generate] pressed
        │
   ┌────▼─────────────────┐   1 Gemini call
   │  gap_analysis(cv,jd) │──────────────►  JSON { sufficient, gaps[] }
   └────┬─────────────────┘
        │
   sufficient? ──yes──►  generate directly (existing flow, remediated prompts)
        │
        no
        │
   render follow-up questions (one per gap, each with an example)
        │
   user types answers  (voice = Phase 4)
        │
   store answers in user_sessions (keyed by JD hash)
        │
   generate CV  ─┐
   cover letter ─┼─►  each prompt gets: resume + verified answers + "do not invent" guardrail
   interview QA ─┘
```

---

## 2. Gap analysis — the one new LLM call

New function `analyze_cv_jd_gaps(resume_text, job_description, language)` in
[cv_generator.py](../cv_generator.py) (sits beside `generate_cv`). **One** structured Gemini
call returning strict JSON:

```json
{
  "sufficient": false,
  "overall_match": 62,
  "gaps": [
    {
      "id": "kubernetes",
      "area": "Kubernetes / container orchestration",
      "why": "JD requires K8s in production; resume shows Docker only",
      "question": "Have you run workloads on Kubernetes in production? What did you do?",
      "example": "e.g. 'At Acme I migrated 12 services to EKS, cutting deploy time 40%.'"
    }
  ]
}
```

Rules:
- `sufficient: true` → **no questions, no extra work**; existing generation runs unchanged
  (aside from the remediated prompt). Keeps cost at *zero extra* for well-matched CVs.
- Cap gaps at **`MAX_GAPS` (default 5)** — one clear question each (client's "one question per
  missing area").
- Every gap **must** include an `example` (client requirement).
- Robust JSON parsing (strip code fences, `json.loads`, fall back to `sufficient:true` on
  parse failure so a bad response never blocks generation).
- Deterministic-ish: low temperature; the call is gated behind the Generate button only
  (never on keystroke), and **memoized per `(resume_hash, jd_hash)` within the session** so
  re-generating the same pair doesn't spend a second call.

**Cost:** exactly **+1 Gemini call** per generation attempt on an under-matched CV; **0** when
sufficient or when served from the session memo.

---

## 3. Disclaimer (verbatim, client-mandated)

Show the exact text from [Feature_list.txt](../Feature_list.txt) before generation, gated by
an acknowledgment checkbox (must tick once per session before the first generate):

> *"Please provide accurate information based on your real experience. CVOLVE PRO can help
> structure and improve your CV, but you are responsible for the accuracy of the information
> you provide. If you enter false or misleading details, you accept full responsibility for
> the final content."*

Verbatim — do not paraphrase. Also shown above the follow-up-questions form.

---

## 4. Streamlit UI flow (session-state driven)

Extends `show_cv_generation_page()` ([app.py:733](../app.py#L733)). A small state machine in
`st.session_state["alignment_stage"]`:

| Stage | UI |
|---|---|
| `idle` | Upload + JD + disclaimer checkbox + **Generate** button |
| `questions` | Per-gap cards: **bold question**, grey *example* caption, `st.text_area` answer, disabled 🎤 "Speak (coming soon)" placeholder. Buttons: **Use my answers & generate** / **Skip & generate** (see §11 decision) |
| `generating` | Spinner → existing generation + preview |

Notes:
- One question per gap, example rendered under each (client requirement).
- Answers rendered via Streamlit's default escaping (no `unsafe_allow_html`).
- Voice button is a visible-but-disabled placeholder so the Phase 4 upgrade path is obvious.

---

## 5. Answer storage — reuse `user_sessions` (no new table)

`user_sessions` is a per-user JSON blob (upsert) via
[save_user_session / get_user_session](../database.py#L432). Store under a namespaced key so
answers persist and can enrich later cover-letter / interview-prep runs for the same JD:

```json
"alignment": {
  "<jd_hash>": {
    "gaps":    [ ...as returned... ],
    "answers": { "kubernetes": "Ran 12 EKS services…", "terraform": "" },
    "updated_at": "2026-07-14T…"
  }
}
```

Keyed by `jd_hash` (sha256 of normalized JD) → the same verified answers automatically feed CV,
cover letter, and interview prep. Empty answers are stored as empty (user skipped that gap).

---

## 6. Applying answers to generation (CV + cover letter + interview)

Answers become a **verified-context block** appended to the inputs of `generate_cv`,
`generate_cover_letter`, and `generate_interview_qa`:

```
ADDITIONAL VERIFIED EXPERIENCE (provided by the candidate, treat as true):
- Kubernetes / container orchestration: Ran 12 EKS services, cut deploy time 40%.
- …
```

Paired with the guardrail (§7). Only **non-empty** answers are included. The three generators
already take `resume_text` + `job_description`; add an optional `extra_context: str = ""`
parameter threaded into their prompts — minimal signature change, backward compatible.

---

## 7. Prompt remediation (the guardrail)

Applied to `generate_cv` (active `prompt_5`), `generate_cover_letter`, `generate_interview_qa`:

**Remove:**
- Every "Fabricate work experience…" line.
- The "N original + M fabricated bullets" distribution math → replace with "use only real
  experience; rephrase, reframe, and emphasize with JD terminology — never invent."

**Add (top of each generation prompt):**
```
HARD RULE — TRUTHFULNESS:
Use ONLY facts present in the résumé and the candidate's verified answers below. Do NOT
invent, fabricate, exaggerate, or assume any employer, role, date, skill, tool, certification,
or metric that is not explicitly supported. You may rephrase real experience using the JD's
terminology and surface genuinely-held skills; you may NOT claim experience the candidate
does not have. If evidence is missing, omit rather than invent.
```

Keep the ATS keyword-optimization guidance, but reframed as "surface real, matching experience
in JD language," not "insert missing experience." ATS scoring (`analyze_cv_ats_score`) is
unaffected mechanically; scores will simply reflect honest content.

---

## 8. Cost & dependencies summary

- **LLM cost:** +1 Gemini call max per generation (gap analysis), 0 when sufficient/memoized.
  Remediation adds no calls. Voice (transcription) stays in **Phase 4**.
- **New deps:** none.
- **DB:** none (reuses `user_sessions`).

---

## 9. Build steps (in order)

1. ✅ `analyze_cv_jd_gaps()` + `parse_gap_analysis()` (fail-open) in `cv_generator.py`.
2. ✅ **Prompt remediation** — deleted the 4 dead fabrication-laden prompt variants
   (`prompt`…`prompt_4`, ~351 lines); hardened the active `prompt_5`, cover-letter `prompt_2`,
   and interview prompt with `TRUTHFULNESS_GUARDRAIL`. No "Fabricate"/"N fabricated bullet"
   instructions remain (regression-tested).
3. ✅ `extra_context` param on `generate_cv` / `generate_cover_letter` /
   `generate_interview_qa` → `build_verified_context_block()` injected into each prompt
   (backward-compatible: defaults to `""`).
4. ✅ `save_alignment_answers()` / `get_alignment_answers()` + `hash_jd()` — `alignment`
   namespace in `user_sessions` (⚠️ auto-save merge caveat noted in code for step 6).
5. ⬜ `app.py`: disclaimer + acknowledgment gate; alignment state machine; questions form.
   *(needs running app)*
6. ⬜ Wire: Generate → gap analysis → (questions | direct) → enriched generation.
   *(needs running app)*
7. ✅ Tests — `tests/test_cv_alignment.py`, 19 hermetic tests (gap-JSON parse/fence/truncate/
   fail-open, verified-block formatting, `hash_jd`, guardrail phrases, **fabrication-removed
   regression guard**). Full suite (aggregator + alignment) = **45 green**.

**Engine + prompt remediation (steps 1–4, 7) done and green.** Remaining (5–6) is the
Streamlit UI + gap-analysis wiring, which needs Postgres + the app running.

---

## 10. Test matrix

| # | Scenario | Handling |
|---|---|---|
| 1 | Well-matched CV | `sufficient:true` → no questions, no extra call |
| 2 | Under-matched CV | up to MAX_GAPS questions, each with an example |
| 3 | Gap analysis returns malformed JSON | fall back to `sufficient:true`; never block generation |
| 4 | Model returns >MAX_GAPS gaps | truncate to MAX_GAPS |
| 5 | User answers some, skips others | only non-empty answers injected + stored |
| 6 | User skips all questions | generate on résumé alone (disclaimer still applies) — see §11 |
| 7 | Re-generate same CV+JD | served from session memo → **0** extra calls |
| 8 | Prompt contains no "Fabricate*" text after remediation | assert via test scanning built prompt |
| 9 | `extra_context` empty | prompts identical to today's (minus fabrication) — backward compatible |
| 10 | Answers persist to cover letter / interview | same `jd_hash` reused; verified block present |
| 11 | Disclaimer not acknowledged | Generate button disabled |
| 12 | XSS via answer text in cards | rendered escaped (no `unsafe_allow_html`) |
| 13 | Non-English (JD/answers) | gap questions returned in selected language |

**Testable without the app:** gap-JSON parsing/truncation/fallback (1,3,4), prompt-remediation
assertion (8,9), context-injection formatting (5). Rest are manual once the app runs.

---

## 11. Decisions (resolved)

1. ✅ **Remediation aggressiveness → FULL HONESTY.** Remove all fabrication instructions; add
   the hard "use only real experience" guardrail (§7). Matches the client's exact requirement.
   ⚠️ Still needs **client sign-off** because it lowers the headline ATS scores the current
   tool produces — flag this explicitly when presenting (it's their stated ask, but the score
   drop should not surprise them).
2. ✅ **Follow-up questions → SKIP ALLOWED.** When gaps exist, the user may *Skip & generate*;
   the CV is then built from the résumé alone, with the honesty guardrail + disclaimer still in
   force. Lowest friction, respects genuine gaps. Answers, when given, still enrich generation.
3. ✅ **Defaults:** `MAX_GAPS = 5`; disclaimer gated by a once-per-session acknowledgment
   checkbox.
