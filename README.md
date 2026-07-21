# Job Matcher

A personal job-hunting assistant that pulls listings from a handful of job
boards into one place, ranks them against your resume, and helps you get
through the actually-applying part faster.

I built this because searching for security/software roles across a dozen
tabs of Indeed, LinkedIn, and company career pages got old fast — and most
of what showed up wasn't even relevant to what I was looking for.

## What it does

- **Aggregates jobs** from Adzuna, JobRight, RemoteOK, The Muse, Remotive,
  Dice, and LinkedIn into one feed.
- **Scores every job** against your uploaded resume — skills, seniority
  level, and location — and shows the best matches first.
- **Hard-filters noise** before scoring: no unrelated roles cluttering a
  "Security Engineer" search, no jobs that require a security clearance or
  citizenship you don't have.
- **Tailors your resume with AI** — Gemini 2.0 Flash reads your LaTeX resume
  and the job description and proposes a structured diff, Groq (Llama 3.3 70B)
  applies it to the LaTeX source, and tectonic recompiles it to a PDF. Your
  original resume is never touched — every run works on a copy.
- **Helps you apply** — an intent engine tracks where you are in the apply
  flow per job (draft → review → applied), and drafts a fit summary and
  keyword-gap diff you can review before sending. Draft prose is generated
  deterministically by default, with an optional HuggingFace-backed provider.
- **Runs on a schedule** — APScheduler re-fetches in the background so new
  matches show up without you asking.

## Why aggregator-first

Earlier versions of this project scraped individual company career pages
(Greenhouse, Lever, Ashby, Workday). That doesn't scale — every company is a
one-off integration, and ATS providers change their markup without warning.
This version only talks to sources built to be aggregated: job boards with
public APIs or stable data feeds, plus one authenticated LinkedIn connector.
Fewer moving parts, way less maintenance.

See [`docs/01-overview.md`](docs/01-overview.md) for the full reasoning and
connector-by-connector notes.

## Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL, Alembic migrations
- **Frontend:** Next.js 16 (App Router) + React 19 + Tailwind
- **Auth:** JWT (email/password, bcrypt-hashed)
- **Scheduling:** APScheduler
- **Connectors:** Adzuna, JobRight, RemoteOK, The Muse, Remotive, Dice
  (Playwright), LinkedIn (authenticated)
- **AI:** Gemini 2.0 Flash + Groq (Llama 3.3 70B) for resume tailoring;
  optional HuggingFace Inference Providers for application-draft prose

## Getting started

**Backend**

```bash
cd backend
pip install -e ".[dev]"
cp ../.env.example .env   # fill in DATABASE_URL, CORS_ORIGINS, etc.
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Or start both at once from the repo root with `./start.ps1` (Windows) /
`./dev.ps1`.

The frontend runs at `http://localhost:3000` (or `:4000` via `npm run dev`,
see `frontend/package.json`) and expects the backend at `:8000`.

## Project layout

```
backend/
  app/
    routers/       — thin route handlers (no business logic)
    workers/       — connectors, matcher, deduper, intent engine, scheduler
    models.py      — SQLAlchemy models
    schemas.py     — Pydantic request/response shapes
  alembic/         — DB migrations
frontend/
  app/             — Next.js routes
  components/      — UI components
  lib/             — API client, auth helpers
  types/           — shared TypeScript types
docs/              — architecture, API contracts, roadmap, execution tracker
```

## Docs

Start with [`docs/01-overview.md`](docs/01-overview.md) for product scope,
then [`docs/02-architecture.md`](docs/02-architecture.md) for the data model
and [`docs/04-api-contracts.md`](docs/04-api-contracts.md) for API shapes.
[`docs/TODO.md`](docs/TODO.md) tracks what's actually done versus planned.

## Status

Actively evolving — this is a personal tool first, not a polished product.
Expect some connectors to be flaky (job boards change their markup and block
scrapers without notice) and some rough edges in the UI. Check
[`docs/TODO.md`](docs/TODO.md) for current state and known gaps.

---

Built by [Harsh Bhaskar](https://github.com/HB0309), with
[Claude Code](https://claude.com/claude-code) as a pair-programming partner
throughout.
