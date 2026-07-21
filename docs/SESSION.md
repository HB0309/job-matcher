# SESSION.md – Current Work Context

Update this file at the end of each session before `/clear`. It is the handoff document for the next session.

---

## Current branch
`feat/frontend-mvp`

## Project status (as of 2026-04-28)

Phase 1 is functionally complete. All backend connectors (Greenhouse, Lever, Ashby), the full fetch-match pipeline, and the Next.js frontend MVP are implemented. The codebase is working but has not been end-to-end verified in a single local run yet.

## What is done

- Backend pipeline: orchestrator, normalizer, security_filter, deduper, matcher, fetch run persistence
- Connectors: Greenhouse, Lever, Ashby (seeded with verified targets)
- Profiles API: POST /profiles, GET /profiles/{profile_id}
- Jobs API: GET /jobs, GET /jobs/{job_id}
- Sources API: GET /sources, GET /source-targets
- Fetch API: POST /fetch-jobs
- Frontend MVP: dashboard, profile upload, fetch button, job table, score breakdown, loading/error states
- Docs: trimmed CLAUDE.md, added docs/git-workflow.md, docs/modules.md, docs/SESSION.md
- Security filter: drops clearance/citizenship-required jobs before scoring

## Known bugs / gaps to fix next

1. **PATCH /profiles/{profile_id} missing** — no way to edit preferred_titles or preferred_level without re-uploading resume. Documented in `docs/04-api-contracts.md`.
2. **ProfileCard "Switch" button broken** — calls `selectProfile` instead of opening the edit/upload form.
3. **toggleExpand swallows errors** — job detail expand has no catch block; API failures show a blank row.
4. **Orchestrator is sequential** — connector fetches run one at a time. Should use `ThreadPoolExecutor` for parallel fetches.
5. **TODO.md section 2** — "Create frontend app structure" and "Set up Next.js app" still unchecked even though frontend exists. Mark complete after verifying it runs.
6. **05-backlog-phases.md** — Phase 0 and Phase 1 items are all unchecked but done. Needs a sweep to mark completed work.

## Next session priorities (in order)

1. Verify local end-to-end: run backend + frontend, upload a resume, fetch jobs, view scored results
2. Fix ProfileCard Switch button bug
3. Add error state to job expand
4. Implement PATCH /profiles/{profile_id}
5. Parallelize orchestrator fetches with ThreadPoolExecutor
6. Write unit tests for matcher and normalizer
7. Sweep 05-backlog-phases.md to mark completed work

## Key decisions / architecture notes

- `preferred_level` is stored as a JSON array in the DB (migration 002). API accepts comma-separated string on POST, converts to array.
- Connector fetches are sequential (for loop in orchestrator.py:58). No async, no threading yet.
- Security filter runs after normalization and before deduplication.
- Deduplication key: `(connector_name, source_target_id, external_id)`.
- Scoring weights: title 35%, skills 40%, level 15%, location 10%.
- Frontend talks to `http://localhost:8000` in dev. Endpoint contract is `docs/04-api-contracts.md`.

## Active files to be aware of

- `backend/app/workers/orchestrator.py` — pipeline entry point
- `backend/app/workers/matcher.py` — scoring logic
- `backend/app/models.py` — SQLAlchemy models
- `backend/app/schemas.py` — Pydantic schemas
- `backend/app/routers/profiles.py` — profile endpoints
- `frontend/app/page.tsx` — main dashboard
- `frontend/components/ProfileCard.tsx` — profile display (has Switch bug)
- `frontend/components/ProfileUpload.tsx` — resume upload form
- `frontend/lib/api.ts` — frontend API client
- `frontend/types/index.ts` — TypeScript types

## How to start the stack locally

```bash
# Backend
cd backend
uvicorn app.main:app --reload

# Frontend
cd frontend
npm run dev
```

---

*Update this file before each /clear. Replace the "Current branch" and "Next session priorities" sections with fresh state.*
