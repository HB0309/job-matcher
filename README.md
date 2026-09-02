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

Full step-by-step setup, from a clean clone to a working app in your browser.

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** (and npm)
- **git**

No Docker or database server install is required for local dev — the default
config uses SQLite. Postgres is supported too (see [Database](#database) below)
but isn't required to get started.

### 1. Clone the repo

```bash
git clone https://github.com/HB0309/job-matcher.git
cd job-matcher
```

### 2. Backend setup

```bash
cd backend
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[dev]"
playwright install chromium   # only needed for the Dice connector
```

Create `backend/.env` (copy from the example at the repo root):

```bash
cp ../.env.example .env
```

`.env` defaults to SQLite and needs no editing to run locally. Open it if you
want to swap to Postgres or add optional connector/AI API keys — see
[Configuration](#configuration) below.

**Apply the database migrations before starting the server — this step is
easy to miss and the app will 500 on resume upload without it:**

```bash
alembic upgrade head
```

Now start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

Leave this running. Confirm it's up by opening `http://127.0.0.1:8000/docs`
in a browser — you should see the FastAPI interactive docs.

### 3. Frontend setup

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
```

Open `frontend/.env.local` and check it reads:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

**Use `127.0.0.1`, not `localhost`.** uvicorn binds to `127.0.0.1` only by
default; if the browser resolves `localhost` to its IPv6 address (`::1`)
first — common on Windows — every API call fails with a generic
`TypeError: Failed to fetch` in the browser console, which is confusing to
debug from that error alone.

Now start the frontend:

```bash
npm run dev
```

The frontend runs at `http://localhost:4000` (pinned in
`frontend/package.json`'s `dev` script — not the Next.js default `:3000`)
and expects the backend at `:8000`.

### 4. Or start both at once

From the repo root, on Windows:

```powershell
./start.ps1   # opens two new PowerShell windows, one per server
# or
./dev.ps1     # runs both in one terminal, auto-restarts either on crash
```

These skip the one-time setup above (venv creation, `pip install`,
`npm install`, `alembic upgrade head`) — run steps 2 and 3 at least once
first.

### 5. First run in the browser

1. Open `http://localhost:4000`.
2. **Register** a new account (email + password — this is a local account,
   not tied to any external service).
3. **Upload a resume** (PDF or DOCX) to create your first profile. Set target
   job titles (e.g. "Software Engineer, Backend Engineer") and preferred
   levels — these drive both the connector search query and the title filter
   that decides which fetched postings are relevant to you.
4. Optionally repeat step 3 to add more profiles (e.g. one per job title
   you're targeting) — "Fetch Jobs" always runs for every profile you have in
   one click and shows one combined list tagging which profile(s) matched
   each posting.
5. Under **2 — Fetch Jobs**, pick which connectors to use (RemoteOK, The
   Muse, Remotive, and JobRight need no API key; Adzuna and LinkedIn need
   credentials — see below) and click **Fetch Jobs**.
6. Browse, filter, and save/mark-applied on the results in the **Jobs** tab.

### Configuration

All settings live in `backend/.env` (see `backend/app/config.py` for the full
list with defaults). Nothing beyond the defaults is required to run the app —
these unlock optional connectors and AI features:

| Variable | Unlocks | Get it from |
|---|---|---|
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna connector | Free at [developer.adzuna.com](https://developer.adzuna.com) |
| `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` | LinkedIn connector (unofficial API — slow, ~4-6 min/run, use a throwaway/secondary account) | Your own LinkedIn login |
| `GEMINI_API_KEY` | AI resume tailoring (Gemini reads your resume + a job description and proposes edits) and semantic job re-ranking | [Google AI Studio](https://aistudio.google.com/) |
| `GROQ_API_KEY` | LaTeX resume editing during tailoring, and the agentic job-matching re-rank/rationale step | [console.groq.com](https://console.groq.com) |
| `HF_API_TOKEN` | Optional LLM-backed application-draft prose (`DRAFTING_PROVIDER=huggingface`); deterministic drafting is the default and needs no key | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |

RemoteOK, The Muse, Remotive, and JobRight need no credentials — they're
public APIs. Resume PDF compilation (for tailored resumes) additionally
requires [tectonic](https://tectonic-typesetting.github.io/) on your `PATH`.

### Database

Local dev defaults to SQLite (`sqlite:///./job_matcher.db`, zero setup). To
use Postgres instead, set `DATABASE_URL=postgresql://user:password@localhost:5432/job_matcher`
in `backend/.env` and re-run `alembic upgrade head` against it before
starting the server.

### Troubleshooting

- **"Failed to fetch" in the browser on every API call** — see the
  `127.0.0.1` vs `localhost` note in step 3 above.
- **500 error uploading a resume, `no column named ...` in the server log**
  — you skipped `alembic upgrade head`; run it against whichever database
  your `.env` points at, then restart the backend.
- **Port 8000 or 4000 already in use / stale process from a previous run** —
  on Windows, `uvicorn --reload` spawns a child worker process that can
  outlive the parent if killed incorrectly; find and stop the real listener
  with `Get-NetTCPConnection -LocalPort 8000` (PowerShell) rather than
  assuming the PID you started it with is still the one holding the port.

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
