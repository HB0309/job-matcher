# Job Matcher – Agents and Flows

## 1. Module responsibilities (summary)

See `docs/modules.md` for the full table.

Key pipeline actors:
- **Orchestrator** — coordinates end-to-end; owns the FetchRun lifecycle
- **Connector** — fetches raw job postings from one source (board API, Playwright scraper, or authenticated API)
- **Normalizer** — maps raw → internal DTO; detects level, extracts skill tags
- **Security filter** — drops clearance/citizenship-required jobs
- **Title filter** — drops jobs whose title has no domain keyword from `preferred_titles`
- **Deduper** — 3-pass deduplication; prevents re-inserting known jobs
- **Matcher** — scores each new job against the profile; weights: skills 35%, level 50%, location 15%
- **Intent engine** — classifies next-best-action for each saved job from current state
- **Application drafter** — generates a job-specific application package

## 2. Connector model

Each connector is a Python class with a single method:

```python
def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]
```

All current connectors are aggregator/social — one virtual `SourceTarget` per connector. The orchestrator passes the same `JobQuery` (containing `preferred_titles`, `preferred_level`, `max_results_per_target`) to every connector so each can adapt the query to its own API format.

### Connector strategies by type

| Connector | Strategy |
|---|---|
| **Adzuna** | REST paginated search per title; `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` required |
| **JobRight** | Next.js internal data API; calls `/_next/data/{buildId}/jobs.json`; caches buildId, re-fetches on 404; descriptions assembled inline from `jobSummary` + `coreResponsibilities` (bullet list) + `requirements` (bullet list) — no extra HTTP calls |
| **RemoteOK** | Official JSON API; one call per title keyword |
| **The Muse** | Public REST API; searches Software Engineering category; maps level strings |
| **Remotive** | Free JSON API; searches per title; strips HTML from descriptions |
| **Dice** | Playwright headless Chromium; stealth flags to bypass bot detection; DOM extraction via `data-testid="job-card"`; extracts title (aria-label), company (company-profile link), location (span regex), posted date; job descriptions fetched separately via httpx GET to SSR detail page (`/job-detail/{guid}`) using `[class*="jobDescription"]` CSS selector (no extra Playwright needed); batched to first 50 per run |
| **LinkedIn** | `linkedin-api` Voyager reverse-engineered API; email+password login; `search_jobs()` per title → job IDs → parallel `get_job()` detail fetch (5 threads); extracts direct apply URL when available |

## 3. Key flows

### 3.1 Profile creation

```
POST /profiles (multipart: file + preferred_titles + preferred_level)
  → resume_parser.extract_profile(file_bytes, filename)
      → PDF: pypdf text extraction
      → DOCX: python-docx paragraph extraction
      → headline: first non-empty line ≤ 120 chars
      → skills: keyword scan against ~200 tech/security canonical terms + 104 alias mappings
             (both resume and job-description extraction share extract_skills() so intersection is symmetric)
             aliases normalize variants → canonical: k8s→kubernetes, golang→go, sklearn→scikit-learn, etc.
      → years_experience: month-range duration summing from date spans
  → Profile row inserted
  → 201 ProfileResponse
```

### 3.2 Fetch & Match

```
POST /fetch-jobs {profile_id, connectors[], max_results_per_target}
  → orchestrator.run_fetch_and_match()
      1. Load profile
      2. Load enabled SourceTargets filtered by connector names
      3. Insert FetchRun + FetchRunTarget stubs → commit (release DB lock)
      4. ThreadPoolExecutor(max_workers=10): connector.fetch_jobs() per target
      5. normalize(raw_jobs) → NormalizedJob list
         - detect normalized_level from title + description
         - extract skill tags from description
      6. filter_disqualifying_jobs() → drop clearance/citizenship
      7. extract_domain_keywords(preferred_titles) → domain_keyword_set
         passes_title_filter(job.title, domain_keywords) → drop mismatches
      8. dedupe(normalized, db, connector_map)
         Pass 1: within-batch fingerprint collapse
         Pass 2: exact (connector_id, source_target_id, external_id) DB check
         Pass 3: fuzzy fingerprint check against existing DB rows
      9. Persist new JobPosting rows
      10. score_jobs(profile, new_jobs)
          - skills_score: Jaccard overlap of profile.skills ∩ job.tags
          - level_score: match between preferred_level and normalized_level
          - location_score: 1.0 if remote/null, 0.5 if US, 0.0 otherwise
          - overall = 0.35 * skills + 0.50 * level + 0.15 * location
      11. Persist JobMatch rows (with fetch_run_id)
      11b. Agentic matching funnel (Stage 2 + 3 — see below)
      12. Update FetchRun status + counts → commit
  → FetchJobsResponse {fetch_run_id, total_jobs_matched, status, ...}
```

### 3.2b Agentic matching funnel (added 2026-08-07)

Runs after Stage 1 (the zero-cost heuristic `score_jobs` above) persists this
run's `JobMatch` rows. Purpose: get a genuinely LLM-reasoned score + rationale
onto the strongest matches (this is what makes it accurate to say postings are
"ranked against a resume with LLMs" — previously only the tailoring step used
an LLM, matching itself was pure heuristic). Cost is bounded by construction —
each stage narrows the pool before the next, more expensive stage runs:

```
Stage 1 (existing, zero cost): score_jobs() over ALL new postings
  → rank by overall_score, keep top 20 (_STAGE1_TOP_N)

Stage 2 (embedder.py, cheap): semantic re-rank via cached embeddings
  - Each JobPosting.embedding computed ONCE at ingestion (persist loop, step 9),
    cached forever — never recomputed for future runs/profiles against the
    same posting.
  - Profile.embedding computed once per resume upload (or lazily on first
    match run if missing), cached on the profile row.
  - Cosine-similarity re-rank the Stage 1 top-20 down to a shortlist of 8
    (_SHORTLIST_SIZE). No pgvector — embeddings are plain JSON float arrays,
    compared in-process with numpy (see embedder.py docstring for why).
  - Degrades gracefully to "first 8 of the Stage 1 order" if no
    GEMINI_API_KEY is configured — never blocks the run.

Stage 3 (agent.py, bounded LLM cost): LangGraph tool-calling agent over the
  8-posting shortlist ONLY — never the full fetched pool.
  - Tools: score_match(job_id) [reasoned 0-1 score + rationale via Groq
    llama-3.3-70b-versatile], draft_bullet(job_id) [one-sentence fit
    rationale, only after score_match], search_job_board(query) [re-filters
    postings already fetched this run that fell outside the Stage 1 top-20 —
    NOT a new live connector call — lets the agent broaden its view if the
    shortlist looks weak], finish.
  - Graph: agent (calls the model) <-> tools (executes the requested calls),
    looping until the model calls finish OR MAX_ITERATIONS=3 is hit
    (hard cost ceiling even if the model never finishes on its own).
  - Result written to JobMatch.explanation as
    "[agentic] score=0.NN — <rationale>\n<draft bullet>" for every job_id the
    agent actually scored (not every shortlist entry — the agent decides
    which postings are worth scoring, that's the point).
  - Degrades gracefully to Stage 1 heuristic scores only if GROQ_API_KEY is
    missing or the shortlist is empty (`stopped_reason` = "no_api_key").

Worst case per run: ~8 shortlist postings, bounded by 3 agent-loop iterations
— a small, predictable number of LLM calls, independent of how many postings
(100+) were actually fetched.
```

### 3.2c Multi-profile fetch (added 2026-08-31)

`POST /fetch-jobs/all` runs 3.2 (+ 3.2b per profile) for every profile a user
owns in one call, via `orchestrator.run_fetch_and_match_for_profiles()`:

```
POST /fetch-jobs/all {connectors[], max_results_per_target}
  → orchestrator.run_fetch_and_match_for_profiles()
      1. Load every profile owned by the authenticated user
      2. Load enabled SourceTargets ONCE (shared — global, not profile-scoped)
      3. group_key = tuple(sorted(profile.preferred_titles))
         → profiles with identical title sets share one fetch pass
      4. Per unique group: create a FetchRun (+ FetchRunTarget stubs) for
         EVERY profile in that group, then run steps 4-7 of 3.2 ONCE for the
         group (parallel fetch, normalize, security filter) — the group's
         single fetch outcome is mirrored onto every profile's own
         FetchRunTarget rows (cheap bookkeeping duplication; the actual HTTP
         calls only happen once per group)
      5. Concatenate every group's normalized+filtered batch, call dedupe()
         ONCE for the whole run → one shared new_jobs pool, one JobPosting
         persisted per unique posting (steps 8-9 of 3.2, run once total)
      6. Per profile (not per group): apply that profile's OWN
         extract_domain_keywords/passes_title_filter over the full combined
         new_jobs pool (catches cross-group overlap correctly), score_jobs(),
         persist JobMatch rows against that profile's own FetchRun, run 3.2b
         scoped to that profile only
      7. Finalise each profile's own FetchRun status + counts → commit once
  → FetchJobsResponse[] — one entry per profile, same shape as 3.2's response
```

The single-profile flow in 3.2/3.2b is unchanged and still used by the
scheduler (`workers/scheduler.py`) for auto-fetch.

### 3.3 Job list query

```
GET /jobs?profile_id=...&limit=5000
  → JOIN job_matches ⨝ job_postings ⨝ connectors
  → ORDER BY overall_score DESC, job_matches.created_at DESC, posted_at DESC
  → JobListItem includes: fetched_at (= job_match.created_at), fetch_run_id
  → Frontend uses fetch_run_id to badge "NEW" and toggle "New only" filter
```

Optional filters: `min_score`, `connector`, `target_id`, `fetch_run_id` (for "New only").

### 3.4 Job detail dialog

```
GET /jobs/{job_id}?profile_id=...
  → Returns raw_description + tags + full score breakdown
  → Frontend dialog shows:
      - Score bars: Overall, Skills, Level, Location (no Title bar)
      - Keyword chips (blue) from job.tags
      - Full description (scrollable)
      - "Preview only" amber badge for Adzuna (500-char cap)
      - Save / Apply buttons
```

### 3.5 Generate application draft

```
POST /application-drafts {profile_id, saved_job_id}
  → Check for existing draft (idempotent)
  → application_drafter.generate_draft(profile, saved_job, job_posting)
      → DeterministicProvider (default):
          fit_summary: template from JobMatch scores + matched skills
          keyword_gap_summary: {matched: profile.skills ∩ job.tags, missing: job.tags - profile.skills}
          tailored_resume_json: structured echo of profile fields
          qa_answers_json: deterministic answers for work_authorization, location, etc.
      → HuggingFaceProvider (opt-in):
          pre-computes deterministic facts (skill overlap, gap list, scores)
          calls HF InferenceClient with deterministic facts in prompt
          falls back to DeterministicProvider on failure
  → ApplicationDraft row inserted (status=review_pending)
  → ApplicationDraftResponse
```

### 3.6 Intent assessment

```
POST /intent/assess {profile_id, saved_job_id}
  → Load saved_job, draft (if any), profile
  → intent_engine.assess(state):
      applied → manual_only
      no draft → prepare_draft
      draft.status == review_pending → review_draft
      draft.status == stale → refresh_draft
      draft.status == approved → start_apply
      draft.status == discarded → prepare_draft
  → {intent, confidence, reasons, recommended_action: {type, label}}
```

### 3.7 Stale draft detection

```
PATCH /profiles/{id} (titles or level changed)
  → application_drafter.mark_stale_for_profile(db, profile_id)
      → Find all ApplicationDraft rows for profile where status in (review_pending, approved)
      → Set status = stale
  → Frontend ProfileCard re-assesses intent → surfaces "N drafts marked stale" banner
```

### 3.8 Tailored resume generation

```
POST /tailored-resumes {profile_id, saved_job_id, user_notes}
  → Load profile, saved_job, job_posting
  → resume_tailor.tailor_resume()

  Step 1 — Gemini analysis (resume_tailor._analyze_with_gemini)
      Load main.tex from resume_latex/
      Build prompt: LaTeX source + JD (capped at 6 000 chars) + user_notes
      Call Gemini 2.0 Flash (gemini-2.0-flash)
        → On 429/RESOURCE_EXHAUSTED: retry with backoff (15s, 30s); after 3 attempts fall through to next model
        → On 404/NOT_FOUND: skip model immediately, try next
        Fall back to gemini-2.0-flash-lite (separate quota bucket, same v1beta endpoint)
      Parse response → JSON diff:
        {professional_summary, skills_table[], experience_bullets{}, projects_include[], project_bullets{}, tailoring_rationale}

  Step 2 — Groq LaTeX edit (resume_tailor._apply_with_groq)
      Model: llama-3.1-8b-instant, max_tokens=16384, temperature=0.1
      Prompt: JSON diff + original .tex source
      On RateLimitError: retry with backoff (5s, 10s, 20s; max 4 attempts)
      Strip markdown fences if present
      Warn if finish_reason=length or \end{document} missing

  Step 3 — tectonic PDF compile
      Write draft_{title}_{id}.tex + resume.cls to temp dir
      Run tectonic.exe main.tex → main.pdf
      Read PDF bytes; delete draft .tex
      On failure: save .tex only (pdf_bytes=None)

  Step 4 — upsert TailoredResume row
      Existing by saved_job_id → update latex_source, pdf_bytes, version+1
      New → insert with version=1
      Commit + refresh → TailoredResumeResponse
```

## 4. Scoring detail

### Domain keyword extraction

```python
_TITLE_GENERIC_WORDS = {
    "engineer", "developer", "specialist", "associate", "manager", "director",
    "lead", "senior", "junior", "staff", "principal", "head", "officer",
    "new", "grad", "graduate", "entry", "level", "ii", "iii", "iv", "i",
    "jr", "sr", "mid", "the", "a", "an", "and", "or", "of", "in", "at",
    "remote", "hybrid", "onsite", "contract", "intern", "internship",
}
# "Security Engineer, New Grad" → {"security"}
# "SOC Analyst" → {"soc", "analyst"}
# "Software Engineer" → {} (all generic) → filter skipped entirely
```

### Level scoring

| Profile preferred_level | Job normalized_level | Score |
|---|---|---|
| Exact match | Exact match | 1.0 |
| `new_grad` | `entry` or `junior` | 0.85 |
| `entry` | `new_grad` or `junior` | 0.7 |
| Within 1 tier | Within 1 tier | 0.5 |
| No normalized_level on job | — | 0.5 (unknown) |
| Mismatch by 2+ tiers | — | 0.0 |

### Skills scoring

Jaccard-like: `len(profile_skills ∩ job_tags) / max(len(job_tags), 1)`, capped at 1.0.

Both sets are canonical: `extract_skills()` normalizes `"k8s"` → `"kubernetes"`, `"golang"` → `"go"` etc. before storage, so a resume with `"k8s"` and a JD with `"kubernetes"` produce a non-zero intersection.

### Location scoring

`1.0` if job location is null, contains "remote", or connector is Remotive/RemoteOK.
`0.5` if US location detected.
`0.0` otherwise.

## 5. Deduplication fingerprint

```python
def _fingerprint(company: str, title: str) -> str:
    c = normalize(strip_company_suffixes(company))   # remove inc/llc/corp etc.
    t = normalize(strip_job_suffixes(title))          # remove remote/contract/hybrid etc.
    return f"{c}|{t}"
```

Example: `"SpaceX Inc"` + `"Product Security Engineer (Remote)"` → `"spacex|product security engineer"`.

## 6. Dedup and re-fetch behaviour

Jobs are re-fetched from APIs on every run (no HTTP response caching). The deduper prevents re-insertion — existing `JobPosting` and `JobMatch` rows are NOT recreated. Old jobs remain visible in the list with their original `fetched_at`. Only genuinely new jobs (pass all 3 dedup passes) get new `JobMatch` rows and appear with the NEW badge.

## 7. Scheduled fetches

APScheduler runs in-process as a background thread. On startup, `scheduler.py` loads all enabled `ScheduledFetch` rows and registers `interval_hours`-based jobs. The schedules router calls `register()`/`unregister()` on CRUD operations.
