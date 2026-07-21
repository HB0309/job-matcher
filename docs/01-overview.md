# Job Matcher – Product Overview

## 1. Vision

A personal job-hunting assistant that:

- Aggregates US-based tech, security, and software roles from major job boards and LinkedIn.
- Uses your uploaded resume and title/level preferences to rank jobs by relevance.
- Filters out noise (clearance-required jobs, domain mismatches) before scoring.
- Runs locally, zero external cost beyond optional API keys.

## 2. Target users and roles

- **Primary user:** You, running locally or on a low-cost host.
- **Secondary users:** A small set of trusted friends in adjacent domains.
- **Supported roles:**
  - Security Analyst / SOC Analyst
  - Security Engineer / Detection Engineer
  - Software Engineer / New Grad / Entry-Level SWE

Initial region is US-focused.

## 3. Problem statement

Manually searching job boards is repetitive and noisy. This tool:
- Pulls jobs from multiple boards into one place
- Hard-filters by domain keyword (no "Retail Associate" showing up in a Security Engineer search)
- Scores by skills, level, and location
- Shows the best matches first with NEW badges for freshly fetched jobs

## 4. Current product direction — Aggregator-first

ATS (company career page) connectors were removed. The system is now **aggregator-first**: all connectors are large job boards or social networks, each acting as a single virtual target.

### Active connectors

| Connector | Type | Auth | Notes |
|---|---|---|---|
| **Adzuna** | Aggregator API | Free API key | Aggregates Indeed + hundreds of boards. 500-char description cap. |
| **JobRight** | Aggregator | None | Next.js internal data API. Full descriptions. |
| **RemoteOK** | Aggregator | None | Remote-only. Official JSON API. Full descriptions. |
| **The Muse** | Aggregator | None | Software Engineering category filter. |
| **Remotive** | Aggregator | None | Remote tech jobs. Full HTML descriptions. |
| **Dice** | Playwright scraper | None | Headless Chromium renders SPA. Slower (~15–30s/title). |
| **LinkedIn** | Social | Email + Password | Authenticated Voyager API. Full descriptions, real apply URLs. ~4–6 min/run. |
| **HiringCafe** | Aggregator | None | Currently 403 blocked. |
| **Indeed** | Aggregator | None | RSS feed gone, currently unavailable. |

### Total: 8 active connectors, 9 virtual targets (one per connector + one LinkedIn target)

## 5. Scoring model

Scoring runs **after** a hard title domain filter:

1. **Hard title filter** — `extract_domain_keywords()` strips generic words from `preferred_titles` (e.g. "Security Engineer" → `{"security"}`). Any job whose title doesn't contain a domain keyword is dropped entirely before scoring.
2. **Scoring weights:** Skills 35%, Level 50%, Location 15%. Title is computed but not weighted — it is used only by the hard filter.
3. **Security filter** — jobs explicitly requiring US security clearance or citizenship are dropped before scoring.

## 6. Repository layout

```
docs/               — planning docs (this file, architecture, API contracts, etc.)
backend/            — FastAPI backend
  app/
    routers/        — thin route handlers
    workers/        — connectors, pipeline, matching
    models.py       — SQLAlchemy models
    schemas.py      — Pydantic request/response shapes
    config.py       — env-var settings
  alembic/          — DB migrations
frontend/           — Next.js UI
  app/page.tsx      — main dashboard
  components/       — UI components
  lib/api.ts        — backend API helpers
  types/index.ts    — TypeScript types
```

## 7. Auth

JWT email/password auth is implemented. Users register/login via `POST /auth/register` and `POST /auth/login`. All profile, job, and saved-job endpoints require a valid Bearer token.

## 8. Apply Extension Layer

An **Application Intelligence Layer** is implemented and wraps the Apply tab:

- **Intent engine** — deterministic state-rule classifier: no draft → `prepare_draft`, draft exists → `review_draft`, draft approved → `start_apply`, profile updated → `refresh_draft`.
- **Application drafter** — generates fit summary, keyword-gap diff, tailored resume JSON, Q&A skeleton. Provider-pluggable: `DeterministicProvider` (default, no network) or `HuggingFaceProvider` (opt-in via `DRAFTING_PROVIDER=huggingface`). Note: HuggingFace/Together is used only for application drafts — the resume tailoring pipeline uses Gemini + Groq separately.
- **Apply tab** — intent-aware CTAs, draft review panel, stale-drafts banner on profile card.

## 9. Constraints

- **Budget:** Zero or near-zero. Adzuna requires a free key. LinkedIn requires your account.
- **Stack:** FastAPI + PostgreSQL + Next.js
- **Region:** US-focused
- **Volume:** ~200 jobs per connector per fetch run (configurable)

## 10. Known limitations

- Dice is slower than other connectors (Playwright browser launch per title search); descriptions fetched via httpx SSR pages (capped at first 50 per run)
- Adzuna descriptions are capped at 500 chars by their API — no workaround
- HiringCafe and Indeed are currently blocked/broken
- LinkedIn takes 4–6 minutes per run at 200 jobs
- Coverage depends on what boards have listings for your search terms
- Re-fetching jobs does not backfill descriptions on existing rows (deduper skips exact matches)

## 11. Future directions

- Fix HiringCafe (Cloudflare bypass) and Indeed (find working data source)
- Add score explanations in UI ("why 72%?")
- Improve skill extraction with canonical taxonomy
- Add multi-user support
- Add notifications (email/push on new high-score jobs)
- Browser-extension assisted apply (Phase 5E)
- Backfill descriptions for existing Dice/JobRight jobs (one-off migration script)
