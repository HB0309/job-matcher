# Job Matcher – Architecture

## 1. High-level system overview

Four layers:

- **Frontend UI (Next.js)** — Resume upload, preferences, fetch controls, jobs dashboard, Apply work queue
- **Backend API (FastAPI)** — REST endpoints for auth, profiles, fetching, jobs, saved jobs, schedules, application drafts, intent assessment
- **Workers / Connectors (Python)** — Resume parsing, job fetching, normalization, deduplication, title filtering, scoring, intent, drafting
- **Database (PostgreSQL)** — users, profiles, connectors, source targets, job postings, match scores, saved jobs, application drafts

## 2. Connector inventory

All connectors are aggregator/social — no ATS (company career page) connectors remain.

| Connector | API style | Auth | Status |
|---|---|---|---|
| `linkedin` | Voyager API via `linkedin-api` package | Email + Password env vars | ✅ Working |
| `remoteok` | Public JSON API | None | ✅ Working |
| `themuse` | Public REST API | None | ✅ Working |
| `adzuna` | REST API | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | ✅ Working (500-char desc cap) |
| `jobright` | Next.js internal data API | None | ✅ Working |
| `remotive` | Public REST API | None | ✅ Working (full descriptions) |
| `dice` | Playwright headless scraper | None | ✅ Working (slower) |
| `hiringcafe` | Next.js SSR | None | ❌ 403 blocked |
| `indeed` | RSS feed | None | ❌ Feed gone |

## 3. Core data flow

### Fetch & Match pipeline

```
User clicks "Fetch Jobs"
  → POST /fetch-jobs
  → orchestrator.py
      1. Load profile (preferred_titles, preferred_level, skills)
      2. Load enabled source targets for selected connectors
      3. Create FetchRun + FetchRunTarget stubs, commit (release DB lock)
      4. ThreadPoolExecutor(max_workers=10): fetch all targets in parallel
      5. normalize() → NormalizedJob list
      6. filter_disqualifying_jobs() → drop clearance/citizenship-required
      7. title filter → extract_domain_keywords() → drop jobs without domain keyword in title
      8. dedupe() → 3-pass deduplication against DB
      9. Persist new JobPosting rows
      10. score_jobs() → JobMatch rows
      11. Finalise FetchRun status
  → GET /jobs?profile_id=...&limit=5000
  → Frontend renders with NEW badges + "New only" toggle
```

### Title filter detail

`extract_domain_keywords(preferred_titles)` strips generic words (engineer, developer, senior, remote, etc.) leaving domain-specific keywords. Example: `["Security Engineer", "SOC Analyst"]` → `{"security", "soc", "analyst"}`. Any job title without a whole-word match against this set is dropped.

### Deduplication (3 passes)

1. **Within-batch fingerprint collapse** — same `company|title` fingerprint → keep best (no connector priority since all are aggregators now)
2. **Exact DB match** — `(connector_id, source_target_id, external_id)` already exists → skip
3. **Cross-source fuzzy fingerprint** — `company|title` fingerprint exists in DB for any connector → skip

## 4. Component breakdown

### 4.1 Frontend (Next.js — App Router)

Single-page dashboard (`frontend/app/page.tsx`):

- **ProfileCard** — shows parsed profile, inline edit for titles/level, stale-drafts banner
- **FetchPanel** — grouped connector selector (Aggregators / Social), color-coded pills, All/Default/None shortcuts, max-results input, last-run summary
- **JobsList** — score table with NEW badge (jobs from latest fetch run), "New only" toggle, connector filter, level filter, min-score slider, search, Best match / Most recent sort toggle, job detail dialog on row click
- **JobDialog** — full description, score breakdown (Overall/Skills/Level/Location), keyword chips, Save/Apply buttons
- **ApplyList** — intent-aware CTAs, IntentChip, ApplicationDraftPanel
- **AppliedList** — cross-profile applied jobs with timestamps
- **SchedulePanel** — auto-fetch, interval dropdown, last/next run display
- **SourcesPanel** — live connector + target summary
- **AuthGate** — wraps app; shows login/register if no token

### 4.2 Backend API (FastAPI)

**Auth:**
- `POST /auth/register` — create account
- `POST /auth/login` — get JWT
- `GET /auth/me` — current user

**Profiles:**
- `GET /profiles` — list profiles
- `POST /profiles` — create from resume upload
- `GET /profiles/{id}` — get profile
- `PATCH /profiles/{id}` — edit titles/level inline; triggers stale-draft marking
- `DELETE /profiles/{id}` — delete profile and cascade

**Jobs:**
- `POST /fetch-jobs` — trigger fetch & match pipeline
- `GET /jobs` — list matched jobs; filters: `profile_id`, `min_score`, `connector`, `target_id`, `fetch_run_id`; sort: `overall_score DESC, created_at DESC, posted_at DESC`
- `GET /jobs/{job_id}` — single job with full description, score breakdown, and `score_explanation` (matched/missing skills, level and location plain-text explanations)

**Sources:**
- `GET /sources` — list connectors
- `GET /source-targets` — list configured targets
- `POST /source-targets` — add target

**Saved jobs:**
- `GET /saved-jobs` — list (optional `?profile_id=`)
- `POST /saved-jobs` — save job
- `PATCH /saved-jobs/{id}` — update status (`saved` → `applied`)
- `DELETE /saved-jobs/{id}` — remove

**Schedules:**
- `GET /schedules`, `POST /schedules`, `PATCH /schedules/{id}`, `DELETE /schedules/{id}`

**Application drafts:**
- `POST /application-drafts` — create draft (idempotent; returns existing if present)
- `GET /application-drafts/{id}` — get draft
- `GET /application-drafts?profile_id=&saved_job_id=` — lookup
- `PATCH /application-drafts/{id}` — approve / discard / edit

**Intent:**
- `POST /intent/assess` — `{profile_id, saved_job_id}` → `{intent, confidence, reasons, recommended_action}`
- `POST /intent/assess-batch` — batch assess for Apply tab

**Tasks:**
- `GET /tasks/{fetch_run_id}` — poll fetch run status

### 4.3 Workers and modules

See `docs/modules.md` for the full table.

Key pipeline modules:
- `orchestrator.py` — end-to-end coordinator
- `normalizer.py` — raw → NormalizedJob; level detection, tag extraction
- `security_filter.py` — drops clearance/citizenship-required jobs
- `matcher.py` — `extract_domain_keywords()`, `passes_title_filter()`, `score_jobs()`; weights: skills 35%, level 50%, location 15%
- `deduper.py` — 3-pass deduplication
- `scheduler.py` — APScheduler background thread; loads schedules on startup
- `resume_tailor.py` — Gemini 2.0 Flash (analysis: resume + JD → structured JSON diff; falls back to `gemini-2.0-flash-lite` on quota/404) → Groq Llama-3.1-8b-instant (LaTeX edit: apply diff to `.tex` source; `max_tokens=16384`; retry backoff on 429) → tectonic (PDF compile); persists `TailoredResume` row

### 4.4 Database (PostgreSQL)

Managed via Alembic migrations. Current schema: 11 tables (migration 007 adds `tailored_resumes`).

## 5. Data model

### users
- `id` (uuid pk), `email` (text unique), `password_hash` (text), `is_active` (bool), `created_at`

### profiles
- `id` (uuid pk), `user_id` (fk → users), `raw_resume_path`, `headline`, `years_experience`, `skills` (jsonb), `preferred_titles` (jsonb), `preferred_level` (jsonb), `created_at`, `updated_at`

### connectors
- `id` (serial pk), `name` (unique), `display_name`, `enabled`, `auth_mode`, `notes`, `created_at`, `updated_at`

### source_targets
- `id` (uuid pk), `connector_id` (fk), `company_name`, `company_key`, `target_slug`, `base_url`, `external_tenant_id`, `region_hint`, `enabled`, `priority`, `config_json` (jsonb), `last_success_at`, `last_failure_at`, `created_at`, `updated_at`

### fetch_runs
- `id` (uuid pk), `profile_id` (fk), `status`, `requested_connectors` (jsonb), `requested_target_ids` (jsonb), `total_jobs_fetched`, `total_jobs_normalized`, `total_jobs_matched`, `started_at`, `finished_at`, `error_summary`

### fetch_run_targets
- `id` (uuid pk), `fetch_run_id` (fk), `source_target_id` (fk), `status`, `jobs_fetched`, `error_message`, `started_at`, `finished_at`

### job_postings
- `id` (uuid pk), `connector_id` (fk), `source_target_id` (fk), `external_id`, `canonical_key`, `title`, `company`, `location`, `url`, `posted_at`, `raw_description`, `normalized_level`, `employment_type`, `tags` (jsonb), `metadata_json` (jsonb), `created_at`, `updated_at`

### job_matches
- `id` (uuid pk), `job_id` (fk), `profile_id` (fk), `fetch_run_id` (fk), `overall_score`, `title_score`, `skills_score`, `level_score`, `location_score`, `explanation` (text, nullable), `created_at`

### saved_jobs
- `id` (uuid pk), `profile_id` (fk), `job_id` (fk), `status` (`saved`|`applied`), `saved_at`, `applied_at`

### scheduled_fetches
- `id` (uuid pk), `profile_id` (fk), `connectors` (jsonb), `interval_hours`, `enabled`, `last_run_at`, `next_run_at`, `created_at`

### application_drafts
- `id` (uuid pk), `profile_id` (fk), `saved_job_id` (fk), `job_id` (fk), `status` (`draft`|`review_pending`|`approved`|`stale`|`discarded`), `fit_summary`, `keyword_gap_summary` (jsonb), `tailored_resume_json` (jsonb), `tailored_resume_version`, `qa_answers_json` (jsonb), `intent_snapshot_json` (jsonb), `confidence_score`, `created_at`, `updated_at`, `approved_at`
- Unique `(profile_id, saved_job_id)`

### tailored_resumes
- `id` (uuid pk), `profile_id` (fk → profiles CASCADE), `job_id` (fk → job_postings CASCADE), `saved_job_id` (fk → saved_jobs CASCADE), `latex_source` (text), `pdf_bytes` (bytea), `user_notes` (text), `gemini_analysis` (jsonb), `version` (int, default 1), `created_at`
- One row per `saved_job_id` (upserted on regenerate; version incremented)

## 6. Scoring model

Weights: **skills 35%, level 50%, location 15%**. Title is computed but only used for the hard filter, not weighted.

Sort order in `GET /jobs`: `overall_score DESC, job_match.created_at DESC, posted_at DESC` — within same score tier, newer fetches appear first.

`GET /jobs` accepts `?fetch_run_id=` to filter to a single run's new matches. Frontend uses this for the "New only" toggle.

## 7. Deployment

### Local development
- All-in-one: `.\dev.ps1` from the project root (starts backend + frontend in parallel, auto-restarts on crashes)
- Backend only: `uvicorn app.main:app --reload --port 8000` from `backend/`
- Frontend only: `npm run dev` from `frontend/` — runs on **port 4000** (Windows excludes port range 2970–3069 which includes 3000)
- PostgreSQL: Docker container (`job_matcher_pg`) — start with `docker start job_matcher_pg`
- Playwright/Chromium: installed via `python -m playwright install chromium`
- CORS: backend allows `http://localhost:3000` and `http://localhost:4000` via `CORS_ORIGINS` env var

### Dependencies worth noting
- `playwright>=1.44` — Dice connector (headless browser)
- `linkedin-api>=2.0` — LinkedIn Voyager API
- `huggingface-hub>=0.27` — optional HF drafting provider
- `python-jose[cryptography]>=3.3` — JWT auth
- `bcrypt>=4.0` — password hashing
- `apscheduler>=3.10` — background fetch scheduling
- `groq` — Groq API client (resume tailoring: LaTeX editing via `llama-3.1-8b-instant`; `max_tokens=16384`; exponential retry backoff on 429)
- `google-genai` — Gemini API client (resume tailoring: analysis step via Gemini 2.0 Flash)
- `tectonic.exe` (bundled at `backend/resume_latex/tectonic.exe`) — self-contained LaTeX compiler for PDF generation

## 8. Future evolution

- Fix HiringCafe (Cloudflare bypass) and Indeed
- Score explanations in UI
- Embeddings/semantic ranking
- Multi-user isolation
- Notifications
- `apply_runs` table + browser-extension apply flow (Phase 5D/5E)
- Resume PDF generation
