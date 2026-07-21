# CLAUDE.md – Job Matcher

## Product direction

Aggregator-first job aggregation and matching tool. Connectors: Adzuna, JobRight, RemoteOK, The Muse, Remotive, Dice (Playwright), LinkedIn. JWT auth, Apply Extension Layer (intent engine + application drafter), APScheduler background fetching. See `docs/05-backlog-phases.md` for roadmap.

## Key docs

- `docs/01-overview.md` — product scope
- `docs/02-architecture.md` — data model
- `docs/03-agents-flows.md` — pipeline flows
- `docs/04-api-contracts.md` — API shapes
- `docs/05-backlog-phases.md` — roadmap
- `docs/TODO.md` — execution tracker (update when work is done)
- `docs/git-workflow.md` — branching and commit rules
- `docs/modules.md` — agent/module responsibilities

## Core rules

1. **Read planning files first** before any architecture, API, schema, or Git changes.
2. **Keep routers thin** — no business logic in route handlers.
3. **Respect module boundaries** — each worker does one job (see `docs/modules.md`).
4. **Sync docs with code** — update relevant `docs/` file + `docs/TODO.md` in the same changeset.
5. **DB changes** — update `models.py`, migrations, `docs/02-architecture.md`, `docs/04-api-contracts.md`, and `docs/TODO.md`.
6. **No regression** — do not reintroduce ATS (Greenhouse/Lever/Ashby) connectors or SQLite.

## Progress tracking

`docs/TODO.md` is the single tracker. Mark tasks complete only when code exists, runs, and docs are updated.

## Frontend

Next.js talks only to endpoints in `docs/04-api-contracts.md`. If response shapes change, update docs + backend models + frontend TypeScript types together.

## Graphify

If `graphify-out/GRAPH_REPORT.md` exists, read it first for navigation context. Rebuild when project structure changes significantly.
```bash
graphify build --path . --output graphify-out
```
