# TODO.md – Job Matcher Execution Tracker

This file tracks real implementation progress. Update it whenever a meaningful task is completed, split, renamed, or removed.

Root workflow instructions and Git rules live in `CLAUDE.md`. Planning phases live in `docs/05-backlog-phases.md`.

## Status legend

- [ ] Not started
- [x] Done
- [~] In progress / partially done
- [!] Blocked / needs decision
- [N/A] Removed or superseded

## 1. Docs and planning

- [x] Write product overview
- [x] Write architecture doc
- [x] Write agents and flows doc
- [x] Write API contracts doc
- [x] Write backlog/phases doc
- [x] Update all docs for aggregator-first direction (removed ATS references)
- [x] Update all docs for Apply Extension Layer
- [x] Update all docs for Dice Playwright scraper + Remotive + LinkedIn fix
- [x] Create docs/modules.md
- [x] Create docs/TODO.md
- [x] Align all docs with code state (score_explanation, tasks response, intent surface field, users UUID pk, canonical_key, explanation col)

## 2. Repo setup

- [x] Create docs/ folder structure
- [x] Place CLAUDE.md at repo root
- [x] Create backend FastAPI app structure
- [x] Create frontend Next.js app structure
- [x] Set up Alembic migrations
- [x] Set up Python dependencies (pyproject.toml)
- [x] Set up Next.js (package.json, tailwind, typescript)

## 3. Database (PostgreSQL)

- [x] users model
- [x] profiles model
- [x] connectors model
- [x] source_targets model
- [x] fetch_runs model
- [x] fetch_run_targets model
- [x] job_postings model
- [x] job_matches model
- [x] saved_jobs model (migration 003)
- [x] scheduled_fetches model (migration 004)
- [x] application_drafts model (migration 005)
- [x] preferred_level as JSON array (migration 002)
- [x] Indexes and uniqueness constraints
- [x] Switch from SQLite WAL to PostgreSQL (QueuePool, pool_pre_ping)

## 4. Auth

- [x] users.password_hash + users.is_active columns (migration 006)
- [x] profiles.user_id FK to users (migration 006)
- [x] bcrypt password hashing
- [x] JWT access token (7-day expiry)
- [x] POST /auth/register
- [x] POST /auth/login
- [x] GET /auth/me
- [x] get_current_user dependency (dependencies.py)
- [x] Bearer token on all profile/job/saved-job endpoints
- [x] Frontend AuthGate component (login/register form if no token)
- [x] Frontend: Authorization header on all API calls (lib/api.ts)

## 5. Profile flow

- [x] Resume upload (multipart/form-data)
- [x] PDF/DOCX text extraction (pypdf, python-docx)
- [x] Skill extraction (~200 tech/security keyword scan)
- [x] Years of experience (month-range duration summing from date spans)
- [x] Headline extraction (first non-empty line ≤ 120 chars)
- [x] GET /profiles
- [x] POST /profiles
- [x] GET /profiles/{id}
- [x] PATCH /profiles/{id} — inline title/level edit without re-upload; triggers stale-draft marking
- [x] DELETE /profiles/{id}
- [x] ProfileCard inline edit
- [x] ProfileCard stale-drafts banner

## 6. Connectors — aggregator-first

### Working
- [x] RemoteOK connector (public JSON API; tag search; one virtual target)
- [x] The Muse connector (public REST API; Software Engineering category; level mapping)
- [x] Adzuna connector (aggregator REST API; ADZUNA_APP_ID + ADZUNA_APP_KEY; 500-char description cap)
- [x] JobRight connector (Next.js _next/data API; buildId caching with 404 invalidation)
- [x] Fixed (2026-08-31): `fetch_jobs()`'s per-title pagination loop had no hard
      page ceiling — only `len(postings) < cap` and the API's own reported
      `totalJobs`, which could be far larger than what's actually reachable/
      unique for a query. When most pages returned already-seen postings this
      ran away (observed: 1400+ pages, minutes of hammering the site, for a
      "Software Engineer" query that should've capped at ~10 pages). Added
      `_MAX_PAGES_PER_TITLE = 25` as an independent hard ceiling; logs a
      warning if hit before reaching `cap`.
- [x] Remotive connector (public REST API; remote tech jobs; HTML-stripped descriptions)
- [x] Dice connector (Playwright headless Chromium; stealth flags; DOM extraction via data-testid="job-card"; company from 2nd anchor in company-profile links; location regex City, ST + Remote/Hybrid/On-Site)
- [x] Dice description fetching via httpx SSR pages (`/job-detail/{guid}`); `[class*="jobDescription"]` selector; capped at 50/run; 1s pause every 10 requests
- [x] JobRight description assembly from `jobSummary` + `coreResponsibilities` (list) + `requirements` (list); no extra HTTP calls needed
- [x] LinkedIn connector (linkedin-api Voyager API; email+password; 5-thread detail fetch; missing SourceTarget row added)

### Removed (2026-09-02)
- [x] Hiring Café connector deleted — Cloudflare-blocked, no realistic bypass worth building
- [x] Indeed connector deleted — Cloudflare bot blocker, RSS feed also gone

### Removed (ATS era — superseded)
- [N/A] Greenhouse connector
- [N/A] Lever connector
- [N/A] Ashby connector
- [N/A] SmartRecruiters connector
- [N/A] Workday connector
- [N/A] All ATS seed files and slug-verify utilities

## 7. Pipeline

- [x] Orchestrator (parallel fetch, ThreadPoolExecutor max_workers=10)
- [x] Normalizer (level detection, skill tag extraction from description)
- [x] Security filter (clearance/citizenship keyword scan on title + description)
- [x] Title filter (extract_domain_keywords strips generic words; passes_title_filter whole-word regex)
- [x] Fixed (2026-08-31): `extract_domain_keywords` required `len(word) > 2`,
      so a title list like `["AI Engineer", "AI Developer"]` stripped
      "engineer"/"developer" as generic AND "ai" for being too short, leaving
      an EMPTY keyword set — which `passes_title_filter` treats as "match
      everything", silently disabling the filter for exactly the profiles
      that need it most (observed matching "Jr Creative Strategist" and
      "Junior UX UI Designer" for an AI Engineer profile). Changed the
      threshold to `len(word) >= 2` so acronyms like AI/ML/QA/UX survive —
      all existing 2-letter stopwords were already covered explicitly by
      `_TITLE_GENERIC_WORDS`, so this doesn't reintroduce noise.
- [x] Deduper (3-pass: within-batch fingerprint collapse, exact DB match, cross-source fuzzy fingerprint)
- [x] Matcher (skills 35%, level 50%, location 15%; title is hard filter only, not weighted)
- [x] FetchRun + FetchRunTarget persistence
- [x] POST /fetch-jobs
- [x] GET /tasks/{fetch_run_id} — poll fetch run status

## 7b. Multi-profile fetch (added 2026-08-31)

Runs the pipeline for every profile a user owns in one click instead of once
per profile. See `docs/02-architecture.md` §3 "Multi-profile fetch" and
`docs/04-api-contracts.md` §2.1b for the full design.

- [x] `orchestrator.run_fetch_and_match_for_profiles()` — groups profiles by
      identical `preferred_titles`, fetches each unique group once, dedupes
      postings once across the whole combined run, then title-filters/scores/
      agentic-reranks per profile against a `FetchRun` of its own
- [x] `POST /fetch-jobs/all` — fetches for every profile owned by the
      authenticated user; existing single-profile `POST /fetch-jobs` untouched
      (still used by the scheduler)
- [x] Frontend: "Fetch Jobs" always runs for all profiles; Jobs tab shows one
      combined list (`CombinedJobItem.matches`) tagged with every profile that
      matched a posting and its own score; save/apply act on the row's primary
      (highest-scoring) profile match
- [x] Verified against live connectors with 3 real profiles: 311 unique
      `job_postings` produced 350 `job_matches` (some postings matched by all
      3 profiles from one shared row — no duplicate postings created)
- [x] Automated integration test (`tests/test_orchestrator_multi_profile.py`,
      in-memory SQLite, `_fetch_one` + `_run_agentic_stage` monkeypatched):
      verifies 2 profiles sharing identical `preferred_titles` produce exactly
      one `_fetch_one` call for their group (not two), a 3rd profile with a
      different title set gets its own call, exactly one `JobPosting` row is
      persisted per unique posting, and per-profile title-filtering + own
      `FetchRun` is correct even though scoring runs over the full combined
      pool

## 8. Jobs API

- [x] GET /jobs — with filters: profile_id, min_score, connector, target_id, fetch_run_id, limit, offset
- [x] GET /jobs/{job_id} — full description + score breakdown
- [x] Sort order: overall_score DESC, job_match.created_at DESC, posted_at DESC
- [x] fetched_at (= job_match.created_at) in JobListItem response
- [x] fetch_run_id in JobListItem response
- [x] fetch_run_id query filter (for "New only" mode)

## 9. Saved jobs

- [x] GET /saved-jobs (optional profile_id; returns cross-profile with inline title/company/connector/profile_headline)
- [x] POST /saved-jobs
- [x] PATCH /saved-jobs/{id} — status: saved → applied (sets applied_at)
- [x] DELETE /saved-jobs/{id}

## 10. Schedules

- [x] GET/POST/PATCH/DELETE /schedules
- [x] APScheduler BackgroundScheduler (in-process background thread)
- [x] scheduled_fetches table (migration 004)
- [x] Schedules re-loaded from DB on server restart
- [x] SchedulePanel in frontend (interval dropdown 6/12/24/48h, enable toggle, last/next run times)

## 11. Sources API

- [x] GET /sources — list connectors
- [x] GET /source-targets — list configured targets
- [x] POST /source-targets — add target

## 12. Frontend MVP

- [x] AuthGate — login/register form if no token
- [x] ProfileCard — inline edit for titles/level, stale-drafts banner
- [x] FetchPanel — aggregator/social groups, color-coded pills, All/Default/None shortcuts, loading state, last-run summary
- [x] JobsList — score table, search, connector filter, level filter, min-score slider, sort toggle (Best match / Most recent), NEW badge, "New only" toggle, job detail dialog
- [x] JobDialog — full description, score breakdown bars, keyword chips, Save/Apply buttons, Adzuna preview badge
- [x] ApplyList — intent-aware CTAs, IntentChip, ApplicationDraftPanel, intent-based row sorting
- [x] AppliedList — cross-profile applied jobs with timestamps, undo support
- [x] SchedulePanel — auto-fetch toggle, interval dropdown, last/next run times
- [x] SourcesPanel — live connector + target summary

## 13. Tailored Resume Pipeline (Phase 4)

Backend
- [x] Alembic migration 007_tailored_resumes.py
- [x] TailoredResume model (models.py) — profile_id/job_id/saved_job_id FKs, latex_source, pdf_bytes, gemini_analysis (jsonb), version
- [x] Pydantic schemas: TailoredResumeCreate, TailoredResumeResponse
- [x] workers/resume_tailor.py — Gemini 2.0 Flash analysis → Groq Llama-3.1-8b-instant LaTeX edit → tectonic PDF compile → upsert
- [x] Gemini 2.0 Flash for Step 1 (analysis): `google.genai.Client`, model `gemini-2.0-flash`; automatic fallback to `gemini-2.0-flash-lite` on 429/404 (separate quota bucket)
- [x] Groq Step 2: `llama-3.1-8b-instant`, `max_tokens=16384` (prevents LaTeX truncation); retry backoff 4 attempts 5s/10s/20s on RateLimitError
- [x] routers/tailored_resumes.py — POST, GET (lookup), GET /{id}/pdf
- [x] Wire router in main.py
- [x] resume_latex/ folder — main.tex, resume.cls, tectonic.exe (v0.15.0)

Frontend
- [x] TailoredResumeCreate, TailoredResumeResponse types in types/index.ts
- [x] API helpers: createTailoredResume, lookupTailoredResume, downloadPdfUrl in lib/api.ts
- [x] ApplicationDraftPanel — Tailored Resume section: notes textarea, Generate button, version badge, tailoring_rationale, Download PDF button, PDF iframe preview
- [x] ApplicationDraftPanel — Job details section: location, level, match %, "View posting" link, collapsible job description (fetched via `api.getJob()`)

Dev tooling
- [x] dev.ps1 — starts backend + frontend in parallel, auto-restarts on crash, color-coded output
- [x] Headline parser: skip education/degree lines (B.Tech, Computer Science etc.) before matching title keywords

## 14. Apply Extension Layer (Phase 3)

Backend
- [x] Alembic migration 005_application_drafts.py
- [x] ApplicationDraft model (models.py)
- [x] Pydantic schemas: ApplicationDraftCreate, ApplicationDraftResponse, ApplicationDraftPatch, IntentAssessRequest, IntentAssessmentResponse, IntentBatchRequest
- [x] workers/intent_engine.py — deterministic state-rule classifier; assess() + assess_batch()
- [x] workers/application_drafter.py — DraftingProvider interface, DeterministicProvider, HuggingFaceProvider, generate_draft(), mark_stale_for_profile()
- [x] Config env vars: DRAFTING_PROVIDER, HF_API_TOKEN, HF_MODEL, HF_PROVIDER
- [x] huggingface-hub>=0.27 dependency
- [x] routers/application_drafts.py (POST/GET/PATCH)
- [x] routers/intent.py (/intent/assess, /intent/assess-batch)
- [x] Wire both routers in main.py
- [x] Stale-draft hook in routers/profiles.py PATCH

Frontend
- [x] ApplicationDraft, IntentAssessment, IntentKind types in types/index.ts
- [x] API helpers: getDraft, createDraft, patchDraft, assessIntent, assessIntentBatch in lib/api.ts
- [x] components/IntentChip.tsx
- [x] components/ApplicationDraftPanel.tsx
- [x] ApplyList.tsx — intent-aware CTAs, IntentChip column, panel hookup, intent-based sort; fixed JS crash from undefined intent rank (`filter(Boolean)` + `?? 99` fallback)
- [x] ApplyList/AppliedList: horizontal scroll (`overflow-x-auto`, `min-w-[860px]`/`min-w-[700px]`), action buttons always visible
- [x] ProfileCard.tsx — stale-drafts banner; w-full (full-width layout)
- [x] Full-width responsive layout: page wrapper max-w-screen-2xl, FetchPanel/ProfileUpload w-full
- [x] Frontend port 4000 (Windows excluded port range 2970–3069 includes 3000)
- [x] CORS: backend allows http://localhost:4000 alongside http://localhost:3000

Verification
- [x] alembic upgrade head succeeds (migration 005 applied)
- [x] Deterministic provider end-to-end smoke test
- [x] HF fallback to deterministic on missing/invalid token
- [x] Stale-draft transition on profile PATCH
- [ ] HuggingFace provider end-to-end smoke test with real HF_API_TOKEN
- [ ] Manual UI walkthrough: prepare → review → approve → edit profile → stale → refresh

## 14. Quality and testing

- [x] Unit tests: matcher (29 tests, all passing)
- [x] Unit tests: normalizer (18 tests, all passing)
- [x] Fixed normalizer crash: `normalizer.py` `_extract_tags`/tag-merge line called `raw.metadata.get("tags")` and raised `AttributeError` when a connector emitted `metadata=None`; now uses `(raw.metadata or {}).get("tags")`. This was a real fetch-pipeline crash risk, not just a test gap.
- [x] Reconciled `matcher.py` `_level_score` test expectations (`test_level_score_adjacent`, `test_level_score_two_apart`) with the documented scoring table in `docs/03-agents-flows.md` ("Level scoring": 0.5 for 1-tier mismatch, 0.0 for 2+ tiers) and the `level_explanation` strings in `routers/jobs.py`. The 0.5-per-tier code was correct; the tests were stale from an earlier 0.3-per-tier formula and have been updated to 0.5/0.0.
- [x] Added `logging.basicConfig(level=logging.INFO, ...)` to `main.py`. Without it, `logging.getLogger(...).info(...)` calls (including `run_metrics.py`'s funnel + `run_metrics_json` summary) were silently dropped by Python's logging lastResort handler (WARNING-level, stderr-only) since nothing in the app configured a root handler — only `print()`-based logs (e.g. `[security_filter]`) were ever visible. Fetch-run instrumentation now actually reaches stdout.
- [x] Registered `remotive` in `seed_connectors.py` and added `seed_remotive_targets.py` — the connector (`workers/connectors/remotive.py`) and registry entry (`workers/registry.py`) were fully implemented and wired, but the connector was never inserted into the `connectors` table and had no seed-target script, so it could never be selected for a fetch despite being documented as done.
- [x] Unit tests: intent_engine (`tests/test_intent_engine.py`) — every `_classify`
      branch (no saved job, applied short-circuit, no draft, stale/approved/
      review_pending/discarded/unexpected draft status), confidence+action
      mapping for all 5 intents, plus a DB-backed `assess()`/`assess_batch()`
      smoke test (real SQLite, not mocks) confirming the query wiring
- [x] Unit tests: application_drafter (`tests/test_application_drafter.py`) —
      `_keyword_gap`/`_confidence_from_match` pure helpers, `DeterministicProvider`
      output shape/formatting, `_select_provider` (incl. HF-token-missing
      fallback), `HuggingFaceProvider` with a mocked `InferenceClient` (valid
      JSON, non-JSON fallback, network-exception fallback — never calls out),
      and DB-backed `generate_draft()`/`mark_stale_for_profile()` (create vs.
      regenerate-and-bump-version, provider-exception fallback). Found and
      fixed a real bug along the way: `mark_stale_for_profile()` mutated
      `intent_snapshot_json` in place then reassigned the same dict object —
      SQLAlchemy's plain (non-`MutableDict`) JSON column silently drops that
      as a no-op change at flush time, so `stale_reason`/`stale_at` never
      actually persisted. Fixed by building a genuinely new dict before mutating.
- [x] Integration test for fetch pipeline end-to-end
      (`tests/test_orchestrator_pipeline.py`) — real in-memory SQLite (not
      mocks) exercising `run_fetch_and_match()`'s full fetch → normalize →
      security filter → title filter → dedupe → persist → score → FetchRun
      finalization chain: happy path, dedupe-on-refetch, partial_success with
      one failed target, failed status when every target fails, no_targets,
      unknown-profile ValueError
- [x] Connector fixture tests (`tests/test_connectors.py`) — mocked-`httpx`
      fixtures for the 5 REST-API connectors (remoteok, themuse, remotive,
      adzuna, jobright): parse-field assertions, missing-field skip, within-
      batch dedup, fetch-failure degrades to `[]`, Adzuna's missing-credentials
      `RuntimeError` propagates intentionally (caught per-target by the
      orchestrator, not swallowed in the connector), and a regression test
      pinning the JobRight `_MAX_PAGES_PER_TITLE` bound. `dice` (Playwright)
      and `linkedin` (linkedin-api auth) are NOT covered — meaningful fixtures
      for those need heavier mocking infrastructure than was in scope here.
- [x] Unit tests: embedder (cosine similarity, rerank ordering, missing-embedding handling — 5 tests)
- [x] Unit tests: agent (no-api-key/empty-shortlist short-circuits, full LangGraph loop via mocked Groq client, max-iterations cap — 4 tests)

## 15b. Agentic matching funnel (added 2026-08-07)

Converts matching from a fixed heuristic-only pipeline into a bounded, genuinely
agentic system — see `docs/03-agents-flows.md` §3.2b for the full design and
`docs/02-architecture.md` §6 for how it composes with the existing Stage 1 scorer.
Motivation: the résumé claimed postings were "ranked... with LLMs", which wasn't
true of the matching step before this (only tailoring used an LLM) — this closes
that gap for real, without spending LLM tokens on every fetched posting.

- [x] Migration 008: `profiles.parsed_experience`, `profiles.embedding`, `job_postings.embedding` (all nullable JSON)
- [x] Stage 0 — `resume_parser.parse_resume_llm()`: one structured Gemini call per resume upload, best-effort, wired into `routers/profiles.py`
- [x] Stage 1 — reused existing `matcher.score_jobs()` unchanged as the funnel's zero-cost first cut (top 20)
- [x] Stage 2 — `embedder.py`: `embed_text()` (Gemini `gemini-embedding-001` — see fix note below), `cosine_similarity()`, `rerank_by_similarity()`; postings embedded once at ingestion (orchestrator persist loop), profile embedded once (lazily if missing); no pgvector, plain JSON float arrays + numpy
- [x] Stage 3 — `agent.py`: LangGraph `StateGraph` agent (`agent`/`tools` nodes, conditional routing, `MAX_ITERATIONS=3` hard cap) with `score_match`/`draft_bullet`/`search_job_board`/`finish` tools over Groq `openai/gpt-oss-120b` (see fix note below); writes to `JobMatch.explanation`
- [x] Wired into `orchestrator.run_fetch_and_match()` via `_run_agentic_stage()` — runs after Stage 1 persist, before FetchRun finalization; every stage degrades gracefully (missing API keys, empty shortlist, agent errors) rather than failing the run
- [x] `docs/02-architecture.md`, `docs/modules.md`, `docs/03-agents-flows.md` updated to match
- [x] Fixed (2026-08-31), verified against real keys for the first time: both
      hardcoded model names had gone stale since this was written —
      `text-embedding-004` 404'd (Gemini's `models.list()` no longer offers
      it; replaced with `gemini-embedding-001`) and `llama-3.3-70b-versatile`
      404'd on Groq (deprecated/removed from their catalog; replaced with
      `openai/gpt-oss-120b`, confirmed to support the tool-calling loop).
      Real run against 3 live profiles (SQLite, not Postgres — this repo's
      actual default, not the Docker/Postgres setup this note originally
      assumed) confirmed genuine LLM scoring end-to-end: `agentic_scored: 2`,
      `agentic_stopped_reason: max_iterations`, real rationale text in
      `JobMatch.explanation`. Model names may need revisiting again in the
      future as these providers continue to churn their catalogs.
- [x] Fixed (2026-08-31): `run_metrics.log_summary()`'s box-drawing "─"
      characters crashed with `UnicodeEncodeError` on Windows consoles whose
      default stdout encoding can't represent them (surfaced once a real run
      actually reached this code path) — replaced with plain ASCII `-`.
- [x] Fixed (2026-09-02): Frontend `JobDialog` now renders `JobMatch.explanation`
      — added `agentic_explanation` to the frontend `JobDetail` type (backend
      schema already had it, frontend type didn't) and a "AI assessment" card
      in `JobDialog` (parses the `"[agentic] score=0.NN — <rationale>\n<draft>"`
      format into a score badge + rationale + draft bullet), shown only when
      that posting was actually scored by the bounded Stage 3 agent
- [ ] Backfill: existing `job_postings`/`profiles` rows have `embedding=NULL` until they're touched by a new fetch/upload — no backfill migration written; fine since Stage 2 degrades gracefully, but worth a one-off script if re-ranking quality on old data matters later

## 15. Next recommended tasks

- [x] Add score explanations in UI ("why 72%?") — skill chips + level/location text under each score bar
- [x] Improve skill extraction with canonical taxonomy — 200 keywords, 104 aliases (k8s→kubernetes, golang→go, sklearn→scikit-learn, etc.)
- [ ] HuggingFace provider end-to-end smoke test
- [ ] Manual UI walkthrough for Apply Extension Layer
- [x] Resume tailoring pipeline — Phase 4 complete: Gemini 2.0 Flash analysis + Groq Llama LaTeX edit + tectonic PDF
- [x] Switch tailoring Step 1 to Gemini 2.0 Flash; fallback chain to `gemini-2.0-flash-lite` on quota/404
- [x] Switch tailoring Step 2 Groq model to `llama-3.1-8b-instant`; max_tokens 4096 → 16384 (fixes LaTeX truncation)
- [ ] Backfill descriptions for existing Dice/JobRight jobs (write a one-off migration script)
- [ ] Apply orchestration backend (Phase 6)

## Observability

- [x] Pipeline stage metrics (`workers/run_metrics.py`): per-stage counts, drop %, and timings logged at end of each fetch/match run (funnel + `run_metrics_json` line). Read the log after a run to capture relevance/dedup/security-filter rates and throughput.
