# Job Matcher – Backlog and Phases

This document tracks the implementation plan in phases. Repository-level working rules and Git workflow rules live in `CLAUDE.md` at the project root.

---

## 1. Phase 0 – Planning and scaffolding ✅ COMPLETE

**Goal:** Establish architecture, docs, Git workflow, and repo skeleton.

- [x] Write overview, architecture, agents/flows, API contracts docs
- [x] Add TODO tracker and Git workflow rules
- [x] Create repo structure (backend + frontend + docs)
- [x] Initialize backend (FastAPI + Alembic + PostgreSQL)
- [x] Initialize frontend (Next.js App Router)
- [x] Set up migrations

---

## 2. Phase 1 – Local MVP (ATS-first) ✅ COMPLETE (then superseded)

**Goal:** End-to-end working system using Greenhouse, Lever, and Ashby company-page connectors.

This phase is complete but the ATS direction was subsequently retired in favor of aggregator-first (Phase 2). The code from Phase 1 that remains useful: resume parser, normalizer, deduper, matcher, orchestrator, saved jobs, schedule infrastructure, and frontend dashboard.

### What was built
- [x] SQLite → PostgreSQL data models and Alembic migrations
- [x] Resume parser (PDF/DOCX, skill extraction, years_experience heuristic)
- [x] Greenhouse, Lever, Ashby, SmartRecruiters, Workday connectors
- [x] Normalizer (level detection, skill tag extraction from descriptions)
- [x] Security filter (drops clearance/citizenship-required jobs)
- [x] Deduper (3-pass: within-batch fingerprint collapse + exact DB match + cross-source fuzzy fingerprint)
- [x] Matcher (scoring: skills 35%, level 50%, location 15%; whole-word domain keyword title filter)
- [x] Orchestrator (parallelized, ThreadPoolExecutor max_workers=10)
- [x] Profiles API (GET/POST/PATCH/DELETE), Jobs API, Sources API
- [x] Saved jobs + Apply/Applied tabs
- [x] APScheduler background scheduling (scheduled_fetches table, SchedulePanel in UI)
- [x] Frontend dashboard: ProfileCard, FetchPanel, JobsList, ApplyList, AppliedList, SchedulePanel, SourcesPanel
- [x] 47 unit tests (matcher + normalizer)

### What was removed
- ATS connectors (Greenhouse, Lever, Ashby, SmartRecruiters, Workday) — unreliable, hard to maintain, low ROI
- ~450 company-specific SourceTarget seed entries
- ATS-specific seed scripts and slug-verify utilities

---

## 3. Phase 2 – Aggregator-first migration ✅ COMPLETE

**Goal:** Replace ATS connectors with large job board and social APIs. One virtual target per connector.

### Direction change rationale
ATS connectors require maintaining per-company slugs, break on schema changes, get Cloudflare-blocked, and cover at most a few hundred companies. Aggregators cover hundreds of thousands of listings each with a single API call.

### Tasks
- [x] Remove all 5 ATS connectors and their seed files
- [x] Add RemoteOK connector (public JSON API)
- [x] Add The Muse connector (public REST API, Software Engineering category)
- [x] Add Adzuna connector (aggregator REST API, `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`)
- [x] Add JobRight connector (Next.js `_next/data` internal API, buildId caching)
- [x] Add Hiring Café connector (Next.js SSR `__NEXT_DATA__` — currently 403 blocked)
- [x] Add Remotive connector (public REST API, remote tech jobs, full descriptions)
- [x] Add Dice connector (Playwright headless Chromium scraper — Dice API dead since 2017; DOM extraction via `data-testid="job-card"`, stealth flags to bypass bot detection)
- [x] Update LinkedIn connector — add missing SourceTarget row in DB; authenticated Voyager API via `linkedin-api` package; email+password env vars
- [x] Update connector registry (9 connectors: linkedin, remoteok, themuse, adzuna, jobright, hiringcafe, indeed, remotive, dice)
- [x] Update seed_connectors.py — remove ATS entries, add aggregator entries
- [x] Redesign FetchPanel — aggregator/social groups, color-coded pills, All/Default/None shortcuts
- [x] Fix sort order — secondary key is `job_match.created_at` (when fetched) not `posted_at` (external, unreliable); newest fetches surface at the same score tier
- [x] Add `fetched_at` and `fetch_run_id` to `JobListItem` schema and API response
- [x] Add `fetch_run_id` filter to `GET /jobs` (used for "New only" mode)
- [x] Add "New only" toggle and NEW badge in JobsList frontend
- [x] JWT auth implementation (`POST /auth/register`, `POST /auth/login`, `GET /auth/me`; Bearer token on all profile/job endpoints)
- [x] PostgreSQL migration (switched from SQLite; standard QueuePool; WAL mode removed)

### Current connector status
| Connector | Status | Notes |
|---|---|---|
| `adzuna` | ✅ Working | 500-char description cap |
| `jobright` | ✅ Working | Full descriptions |
| `remoteok` | ✅ Working | Remote-only |
| `themuse` | ✅ Working | Software Engineering category |
| `remotive` | ✅ Working | Full descriptions |
| `dice` | ✅ Working | Playwright; ~15–30s/title |
| `linkedin` | ✅ Working | ~4–6 min/run |

`hiringcafe` and `indeed` were removed entirely on 2026-09-02 (Cloudflare-blocked,
no realistic fix) — see §"Removed connectors" below.

---

## 4. Phase 3 – Apply Extension Layer (first slice) ✅ COMPLETE

**Goal:** Turn the Apply tab into an intent-aware work queue with deterministic application drafting.

- [x] `application_drafts` table + Alembic migration `005_application_drafts.py`
- [x] `ApplicationDraft` model + Pydantic schemas
- [x] `workers/intent_engine.py` — deterministic state-rule classifier (`prepare_draft`, `review_draft`, `refresh_draft`, `start_apply`, `manual_only`)
- [x] `workers/application_drafter.py` — `DraftingProvider` interface + `DeterministicProvider` (default, no network) + `HuggingFaceProvider` (opt-in via `DRAFTING_PROVIDER=huggingface`)
- [x] Config: `DRAFTING_PROVIDER`, `HF_API_TOKEN`, `HF_MODEL`, `HF_PROVIDER` env vars
- [x] `routers/application_drafts.py` and `routers/intent.py`
- [x] Stale-draft hook in `routers/profiles.py` PATCH — marking drafts stale on profile update
- [x] Frontend: `IntentChip`, `ApplicationDraftPanel`, intent-aware CTAs in `ApplyList`, stale-drafts banner in `ProfileCard`

---

## 4.5. Completed mid-phase improvements

- [x] Dice description fetching — httpx SSR pages (`/job-detail/{guid}`); `[class*="jobDescription"]` selector; capped at 50/run; no extra Playwright needed
- [x] JobRight descriptions — assembled inline from `jobSummary` + `coreResponsibilities` (list) + `requirements` (list)
- [x] Resume tailoring Step 1 switched to Gemini 2.0 Flash (`google.genai`); automatic fallback to `gemini-2.0-flash-lite` on quota/404 (separate free-tier bucket, same v1beta endpoint)
- [x] Resume tailoring Step 2 switched to Groq `llama-3.1-8b-instant` (8B, higher TPM headroom); `max_tokens=16384` (prevents LaTeX truncation); retry backoff on 429 (5s/10s/20s)
- [x] Frontend full-width responsive layout (max-w-screen-2xl, w-full components)
- [x] Apply tab / Applied tab horizontal scroll + button overflow fix
- [x] ApplicationDraftPanel job details section (location, level, match %, collapsible description)
- [x] Frontend port 4000; CORS updated for port 4000

---

## 5. Phase 4 – Connector improvements and coverage

**Goal:** Improve Dice reliability, widen job coverage.

- [x] HiringCafe and Indeed removed entirely (2026-09-02) rather than fixed —
      both Cloudflare-blocked with no realistic bypass worth the effort
- [ ] Improve Dice scraper reliability — currently dependent on DOM structure stability
- [ ] Add score explanations in UI ("why 72%?")
- [ ] Improve skill extraction with canonical taxonomy (normalize synonyms: `k8s ↔ kubernetes`)
- [ ] Title synonym matching (`soc analyst ↔ security analyst`)
- [ ] Fetch retry/backoff per target (currently no retry on transient failures)
- [ ] Import flow for large job result sets (currently capped at 200/connector)

---

## 6. Phase 5 – Drafting upgrades

**Goal:** Improve application draft quality.

- [ ] Structured experience extraction in `resume_parser.py` (sections, bullets, projects)
- [ ] Bullet-level resume tailoring in `HuggingFaceProvider`
- [ ] Q&A answer library per profile (cached free-text answers reused across jobs)
- [ ] Multi-version drafts (`tailored_resume_version`)
- [ ] Right-side drawer for draft review (vs current modal)
- [ ] Inline edit of tailored bullets and Q&A answers
- [ ] Bulk approve / regenerate
- [ ] Filter Apply tab by intent

---

## 7. Phase 6 – Apply orchestration (backend)

**Goal:** Backend groundwork for browser-extension apply.

- [ ] `apply_runs` table + migration
- [ ] `workers/apply_orchestrator.py`
- [ ] `POST /apply-plans` (build plan from approved draft)
- [ ] `POST /apply-runs/{id}/events` (extension-driven progress events)
- [ ] `GET /jobs/resolve-by-url` (fuzzy-match external ATS URL to known `job_id`)

---

## 8. Phase 7 – Browser extension v1

**Goal:** Semi-automated form-fill with user confirmation before submit.

- [ ] `packages/browser-extension/` scaffold (MV3, `background.js`, `content.js`, popup)
- [ ] ATS page detection (Greenhouse, Lever, LinkedIn Easy Apply, Workday)
- [ ] URL → job_id resolve via backend
- [ ] Form fill from `ApplicationDraft.qa_answers_json` (label-matching heuristic)
- [ ] File upload of tailored PDF resume
- [ ] Highlight filled fields (green) / missing fields (yellow)
- [ ] Pause-before-submit checkpoint (user reviews → clicks Submit themselves)
- [ ] Progress events back to backend

---

## 9. Stretch ideas

- [ ] Resume PDF generation + download
- [ ] Cover letter draft support
- [ ] Company watchlists
- [ ] Notifications (email/push on new high-score jobs)
- [ ] Multi-user support
- [ ] Export to CSV / Notion
- [ ] Feedback loop for match training (thumbs-up/down on job cards)
- [ ] Embeddings / semantic ranking (beyond keyword Jaccard)

---

Keep this file aligned with real implementation. If scope changes, update this document and `docs/TODO.md`.
