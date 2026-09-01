# Job Matcher – API Contracts

Base URL (development): `http://localhost:8000`

All responses are JSON. Timestamps are ISO 8601 strings.

All endpoints (except `/auth/*`) require a valid Bearer JWT token in the `Authorization` header.

---

## 0. Authentication

### 0.1 Register

**Endpoint:** `POST /auth/register`

**Request**
```json
{ "email": "user@example.com", "password": "s3cr3t" }
```

**Response 201**
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```

**Errors** — `400` email already registered

---

### 0.2 Login

**Endpoint:** `POST /auth/login`

**Request**
```json
{ "email": "user@example.com", "password": "s3cr3t" }
```

**Response 200**
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```

**Errors** — `401` invalid credentials

---

### 0.3 Current user

**Endpoint:** `GET /auth/me`

**Response 200**
```json
{ "id": 1, "email": "user@example.com", "is_active": true }
```

---

## 1. Profiles

### 1.1 Create profile

**Endpoint:** `POST /profiles`

**Request (multipart/form-data):**
- `resume` (file, required) — PDF or DOCX
- `preferred_titles` (string, required) — comma-separated titles (e.g. `"Security Engineer,SOC Analyst"`)
- `preferred_level` (string, required) — comma-separated levels (e.g. `"entry,junior"`)

**Response 201**
```json
{
  "profile_id": "uuid",
  "headline": "Entry-level Security Engineer",
  "years_experience": 1,
  "skills": ["python", "splunk", "wazuh", "linux"],
  "preferred_titles": ["Security Engineer", "SOC Analyst"],
  "preferred_level": ["entry", "junior"],
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z"
}
```

**Errors** — `400` invalid input, `500` parsing failure

---

### 1.2 List profiles

**Endpoint:** `GET /profiles`

**Response 200** — array of `ProfileResponse` objects (same shape as 1.3)

---

### 1.3 Get profile

**Endpoint:** `GET /profiles/{profile_id}`

**Response 200**
```json
{
  "profile_id": "uuid",
  "headline": "Entry-level Security Engineer",
  "years_experience": 1,
  "skills": ["python", "splunk", "wazuh", "linux"],
  "preferred_titles": ["Security Engineer", "SOC Analyst"],
  "preferred_level": ["entry", "junior"],
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z"
}
```

---

### 1.4 Update profile preferences

**Endpoint:** `PATCH /profiles/{profile_id}`

**Description:** Update preferred titles or level without re-uploading a resume. Triggers stale-draft marking for any existing `review_pending` or `approved` drafts.

**Request**
```json
{
  "preferred_titles": ["Security Engineer", "Software Engineer"],
  "preferred_level": ["entry", "junior"]
}
```

**Response 200** — same shape as `GET /profiles/{profile_id}`

---

### 1.5 Delete profile

**Endpoint:** `DELETE /profiles/{profile_id}`

**Description:** Deletes profile and cascades to fetch runs, job matches, saved jobs, and application drafts.

**Response 204** — no content

---

## 2. Fetch jobs

### 2.1 Trigger fetch & match

**Endpoint:** `POST /fetch-jobs`

**Description:** Triggers a full fetch-and-match pipeline run. All connector fetches are parallelized (ThreadPoolExecutor, max_workers=10). Returns when the run is complete.

**Request**
```json
{
  "profile_id": "uuid",
  "connectors": ["adzuna", "jobright", "remoteok", "themuse", "remotive", "dice", "linkedin"],
  "target_ids": [],
  "max_results_per_target": 200
}
```

**Request fields**
- `profile_id` (string, required)
- `connectors` (array[string], optional) — subset of the registered connector names; defaults to all enabled connectors
- `target_ids` (array[string], optional) — if provided, restricts to these specific `source_target` UUIDs
- `max_results_per_target` (integer, optional, default 200)

**Available connectors**
| Name | Type | Notes |
|---|---|---|
| `adzuna` | REST API | Requires `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`; 500-char description cap |
| `jobright` | Next.js data API | Full descriptions |
| `remoteok` | Public JSON API | Remote-only |
| `themuse` | Public REST API | Software Engineering category filter |
| `remotive` | Public REST API | Remote tech jobs; full descriptions |
| `dice` | Playwright scraper | Headless Chromium; slower (~15–30s/title) |
| `linkedin` | Voyager API | Requires `LINKEDIN_USERNAME` + `LINKEDIN_PASSWORD`; ~4–6 min/run |
| `hiringcafe` | Next.js SSR | 403 blocked — do not use |
| `indeed` | RSS | Feed gone — do not use |

**Response 200**
```json
{
  "fetch_run_id": "uuid",
  "profile_id": "uuid",
  "connectors": ["adzuna", "jobright", "remoteok"],
  "target_count": 7,
  "total_jobs_fetched": 520,
  "total_jobs_normalized": 510,
  "total_jobs_matched": 63,
  "failed_targets": [
    {
      "target_id": "uuid",
      "connector": "dice",
      "company_name": "Dice",
      "error": "Playwright timeout"
    }
  ],
  "status": "partial_success"
}
```

**Status values:** `success` | `partial_success` | `failed` | `no_targets`

**Errors** — `400` invalid request, `404` profile not found, `500` pipeline error

---

### 2.1b Trigger fetch & match for all profiles (added 2026-08-31)

**Endpoint:** `POST /fetch-jobs/all`

**Description:** Runs the fetch-and-match pipeline once for every profile owned by the authenticated user. Profiles sharing identical `preferred_titles` are grouped and share one external connector fetch pass — postings are deduped once across the whole combined run so no profile combination ever creates duplicate `job_postings` rows. Each profile still gets its own `FetchRun`, its own title-filter, its own scores, and its own bounded agentic re-rank (see `docs/03-agents-flows.md` §3.2b), exactly as `POST /fetch-jobs` does per-profile — this endpoint just batches that work instead of requiring one call per profile. See `docs/02-architecture.md` §3 "Multi-profile fetch" for the grouping/dedupe mechanics.

**Request**
```json
{
  "connectors": ["remoteok", "themuse", "remotive", "adzuna"],
  "target_ids": [],
  "max_results_per_target": 200
}
```

Same fields as `POST /fetch-jobs`, minus `profile_id` — it always targets every profile the authenticated user owns.

**Response 200** — array of the same shape as `POST /fetch-jobs`'s response, one entry per profile:
```json
[
  {
    "fetch_run_id": "uuid",
    "profile_id": "uuid-1",
    "connectors": ["adzuna", "remoteok", "remotive", "themuse"],
    "target_count": 6,
    "total_jobs_fetched": 249,
    "total_jobs_normalized": 245,
    "total_jobs_matched": 25,
    "failed_targets": [],
    "status": "partial_success"
  },
  {
    "fetch_run_id": "uuid",
    "profile_id": "uuid-2",
    "connectors": ["adzuna", "remoteok", "remotive", "themuse"],
    "target_count": 6,
    "total_jobs_fetched": 358,
    "total_jobs_normalized": 351,
    "total_jobs_matched": 14,
    "failed_targets": [],
    "status": "partial_success"
  }
]
```

`total_jobs_fetched`/`total_jobs_normalized` reflect that profile's own title-group fetch (not a grand total across all groups); `total_jobs_matched` is that profile's own post-title-filter, post-scoring count.

**Errors** — `404` if the user has no profiles, `500` pipeline error

---

### 2.2 Poll fetch run status

**Endpoint:** `GET /tasks/{fetch_run_id}`

**Response 200**
```json
{
  "fetch_run_id": "uuid",
  "profile_id": "uuid",
  "status": "running",
  "started_at": "2026-05-09T14:00:00Z",
  "finished_at": null,
  "total_jobs_fetched": 120,
  "total_jobs_normalized": 118,
  "total_jobs_matched": 18,
  "error_summary": null,
  "targets": [
    {
      "target_id": "uuid",
      "status": "done",
      "jobs_fetched": 120,
      "error_message": null
    }
  ]
}
```

---

## 3. Jobs

### 3.1 List matched jobs

**Endpoint:** `GET /jobs`

**Query parameters**
- `profile_id` (required)
- `min_score` (optional, float 0–1)
- `connector` (optional, e.g. `"adzuna"`)
- `target_id` (optional, UUID)
- `fetch_run_id` (optional, UUID) — filter to a single run's new matches ("New only" mode)
- `limit` (optional, default 5000)
- `offset` (optional, default 0)

**Sort order:** `overall_score DESC, job_match.created_at DESC, posted_at DESC`

**Response 200**
```json
{
  "profile_id": "uuid",
  "jobs": [
    {
      "job_id": "uuid",
      "connector": "adzuna",
      "source_target_id": "uuid",
      "company": "Acme Security",
      "title": "Security Engineer",
      "location": "Remote, United States",
      "url": "https://www.adzuna.com/details/123",
      "posted_at": "2026-05-08T00:00:00Z",
      "fetched_at": "2026-05-09T14:05:00Z",
      "fetch_run_id": "uuid",
      "normalized_level": "entry",
      "tags": ["python", "siem", "linux"],
      "overall_score": 0.88,
      "title_score": 0.91,
      "skills_score": 0.86,
      "level_score": 1.0,
      "location_score": 1.0
    }
  ]
}
```

**Notes on `fetched_at` vs `posted_at`:** `fetched_at` = `job_match.created_at` (when we ran the match). `posted_at` = when the job was posted externally (may be null or inaccurate). The sort uses `fetched_at` as the secondary key so jobs from the most recent fetch run appear above older duplicate fetches at the same score tier.

---

### 3.2 Get single job detail

**Endpoint:** `GET /jobs/{job_id}`

**Query parameters**
- `profile_id` (required)

**Response 200**
```json
{
  "job_id": "uuid",
  "connector": "adzuna",
  "source_target_id": "uuid",
  "company": "Acme Security",
  "title": "Security Engineer",
  "location": "Remote, United States",
  "url": "https://www.adzuna.com/details/123",
  "posted_at": "2026-05-08T00:00:00Z",
  "raw_description": "Full job description text...",
  "normalized_level": "entry",
  "tags": ["python", "siem", "linux"],
  "scores": {
    "overall": 0.88,
    "title": 0.91,
    "skills": 0.86,
    "level": 1.0,
    "location": 1.0
  },
  "score_explanation": {
    "matched_skills": ["python", "linux"],
    "missing_skills": ["aws", "kubernetes"],
    "skill_count_job": 5,
    "skill_count_profile": 12,
    "level_explanation": "exact level match",
    "location_explanation": "remote (full score)"
  },
  "agentic_explanation": "[agentic] score=0.82 — strong overlap on FastAPI/Postgres, seniority matches new-grad tier\nBuilt a full-stack platform on the exact stack this posting names, including JWT auth and REST API design."
}
```

`agentic_explanation` (added 2026-08-07) — null unless the Stage 3 LangGraph agent actually scored this posting (see `docs/03-agents-flows.md` §3.2b); the agent only scores a bounded shortlist per fetch run, so most postings will have `null` here even on runs where the funnel ran successfully.

**`score_explanation` values**

`level_explanation` examples: `"exact level match"`, `"1 tier above preferred"`, `"2 tiers from preferred"`, `"level not listed (scored as partial)"`.

`location_explanation` examples: `"remote (full score)"`, `"US-based"`, `"non-US location"`, `"location not listed"`.

**Note:** Adzuna descriptions are capped at 500 chars by their API. The frontend shows an "Adzuna preview only" amber badge for these jobs.

---

## 4. Connectors and targets

### 4.1 List connectors

**Endpoint:** `GET /sources`

**Response 200**
```json
{
  "sources": [
    {"name": "adzuna", "display_name": "Adzuna", "enabled": true},
    {"name": "jobright", "display_name": "JobRight", "enabled": true},
    {"name": "remoteok", "display_name": "RemoteOK", "enabled": true},
    {"name": "themuse", "display_name": "The Muse", "enabled": true},
    {"name": "remotive", "display_name": "Remotive", "enabled": true},
    {"name": "dice", "display_name": "Dice", "enabled": true},
    {"name": "linkedin", "display_name": "LinkedIn", "enabled": true},
    {"name": "hiringcafe", "display_name": "Hiring Café", "enabled": true},
    {"name": "indeed", "display_name": "Indeed", "enabled": true}
  ]
}
```

---

### 4.2 List source targets

**Endpoint:** `GET /source-targets`

**Query parameters**
- `connector` (optional)
- `enabled_only` (optional, default true)

**Response 200**
```json
{
  "targets": [
    {
      "id": "uuid",
      "connector": "adzuna",
      "company_name": "Adzuna",
      "base_url": "https://api.adzuna.com",
      "enabled": true,
      "priority": 100,
      "last_success_at": "2026-05-09T14:05:00Z"
    }
  ]
}
```

---

### 4.3 Create source target

**Endpoint:** `POST /source-targets`

**Request**
```json
{
  "connector": "adzuna",
  "company_name": "Adzuna",
  "company_key": "adzuna",
  "base_url": "https://api.adzuna.com",
  "enabled": true,
  "priority": 100,
  "config": {}
}
```

**Response 201**
```json
{
  "id": "uuid",
  "connector": "adzuna",
  "company_name": "Adzuna",
  "enabled": true
}
```

---

## 5. Saved jobs

### 5.1 List saved jobs

**Endpoint:** `GET /saved-jobs`

**Query parameters**
- `profile_id` (optional) — if omitted, returns saved jobs for ALL profiles of the current user

**Response 200**
```json
{
  "saved_jobs": [
    {
      "id": "uuid",
      "profile_id": "uuid",
      "job_id": "uuid",
      "status": "saved",
      "saved_at": "2026-05-09T14:10:00Z",
      "applied_at": null,
      "title": "Security Engineer",
      "company": "Acme Security",
      "location": "Remote",
      "url": "https://...",
      "connector_name": "adzuna",
      "overall_score": 0.88,
      "profile_headline": "Entry-level Security Engineer"
    }
  ]
}
```

---

### 5.2 Save a job

**Endpoint:** `POST /saved-jobs`

**Request**
```json
{ "profile_id": "uuid", "job_id": "uuid" }
```

**Response 201** — same shape as one item from 5.1

---

### 5.3 Update saved job status

**Endpoint:** `PATCH /saved-jobs/{saved_job_id}`

**Request**
```json
{ "status": "applied" }
```

Sets `applied_at` to now when transitioning to `applied`.

**Response 200** — same shape as one item from 5.1

---

### 5.4 Remove saved job

**Endpoint:** `DELETE /saved-jobs/{saved_job_id}`

**Response 204** — no content

---

## 6. Schedules

### 6.1 List schedules

**Endpoint:** `GET /schedules`

**Response 200** — array of schedule objects

### 6.2 Create schedule

**Endpoint:** `POST /schedules`

**Request**
```json
{
  "profile_id": "uuid",
  "connectors": ["adzuna", "jobright", "remoteok"],
  "interval_hours": 24,
  "enabled": true
}
```

**Response 201** — schedule object with `id`, `next_run_at`, `last_run_at`

### 6.3 Update schedule

**Endpoint:** `PATCH /schedules/{schedule_id}`

**Request** — any subset of `{connectors, interval_hours, enabled}`

**Response 200** — updated schedule object

### 6.4 Delete schedule

**Endpoint:** `DELETE /schedules/{schedule_id}`

**Response 204** — no content

---

## 7. Application drafts and intent

These endpoints power the Apply Extension Layer. See `docs/03-agents-flows.md` §3.5–3.7 for behavior detail.

### 7.1 Create or fetch application draft

**Endpoint:** `POST /application-drafts`

**Description:** Idempotent — returns the existing draft for `(profile_id, saved_job_id)` if one exists; otherwise generates a new one. If an existing draft has `status="stale"`, regenerates it.

**Request**
```json
{
  "profile_id": "uuid",
  "saved_job_id": "uuid"
}
```

**Response 200/201**
```json
{
  "id": "uuid",
  "profile_id": "uuid",
  "saved_job_id": "uuid",
  "job_id": "uuid",
  "status": "review_pending",
  "fit_summary": "Solid fit on Python and SIEM tooling; weaker on cloud-native incident response.",
  "keyword_gap_summary": {
    "matched": ["python", "splunk", "linux"],
    "missing": ["aws", "kubernetes"]
  },
  "tailored_resume_json": { "headline": "...", "skills": [...] },
  "tailored_resume_version": 1,
  "qa_answers_json": {
    "work_authorization": "Authorized to work in the United States.",
    "sponsorship": "No sponsorship required.",
    "location": "Open to remote roles.",
    "why_this_role": null
  },
  "confidence_score": 0.78,
  "created_at": "2026-05-09T15:00:00Z",
  "updated_at": "2026-05-09T15:00:00Z",
  "approved_at": null
}
```

**Errors** — `400` invalid input, `404` profile or saved job not found

---

### 7.2 Get draft by id

**Endpoint:** `GET /application-drafts/{draft_id}`

**Response 200** — same shape as 7.1

---

### 7.3 Look up draft for a saved job

**Endpoint:** `GET /application-drafts`

**Query parameters**
- `profile_id` (required)
- `saved_job_id` (required)

**Response 200** — same shape as 7.1, or `404` if none exists

---

### 7.4 Patch draft

**Endpoint:** `PATCH /application-drafts/{draft_id}`

**Request** — all fields optional
```json
{
  "status": "approved",
  "qa_answers_json": { ... },
  "tailored_resume_json": { ... }
}
```

**Status transitions**
- `review_pending` → `approved` (sets `approved_at`)
- `review_pending` → `discarded`
- `approved` → `review_pending` (clears `approved_at`)
- any → `stale` (system-driven; also allowed manually for testing)

**Response 200** — full updated draft

---

### 7.5 Assess intent for one saved job

**Endpoint:** `POST /intent/assess`

**Request**
```json
{
  "profile_id": "uuid",
  "saved_job_id": "uuid",
  "surface": "apply_tab",
  "job_id": null,
  "page_url": null
}
```

All fields except `profile_id` are optional. `surface` defaults to `"apply_tab"`.

**Surface values:** `"apply_tab"` | `"job_detail"` | `"browser_extension"` | `"profile_edit"` | `"dashboard"`

**Response 200**
```json
{
  "surface": "apply_tab",
  "profile_id": "uuid",
  "saved_job_id": "uuid",
  "job_id": null,
  "intent": "review_draft",
  "confidence": 0.95,
  "reasons": ["draft exists", "status is review_pending"],
  "recommended_action": {
    "type": "open_draft_panel",
    "label": "Review draft"
  }
}
```

**Intent values**

| Intent | Trigger |
|---|---|
| `prepare_draft` | No draft exists |
| `review_draft` | Draft exists with `status=review_pending` |
| `refresh_draft` | Draft exists with `status=stale` |
| `start_apply` | Draft exists with `status=approved` |
| `manual_only` | Saved job already `status=applied` |

---

### 7.6 Batch intent assessment

**Endpoint:** `POST /intent/assess-batch`

**Request**
```json
{
  "profile_id": "uuid",
  "saved_job_ids": ["uuid", "uuid", "uuid"],
  "surface": "apply_tab"
}
```

**Response 200** — array of objects matching the 7.5 response shape

---

---

## 8. Tailored resumes

### 8.1 Generate tailored resume

**Endpoint:** `POST /tailored-resumes`

**Description:** Runs the two-step AI pipeline: **Gemini 2.0 Flash** analyses the resume + JD → produces a structured JSON diff (falls back to `gemini-2.0-flash-lite` automatically on quota/404) → **Groq Llama-3.1-8b-instant** applies the diff to the LaTeX source (`max_tokens=16384`) → tectonic compiles to PDF. Upserts a `TailoredResume` row (increments version on regenerate). Groq calls retry with exponential backoff (5s/10s/20s) on 429 rate-limit errors.

**Request**
```json
{
  "profile_id": "uuid",
  "saved_job_id": "uuid",
  "user_notes": "Focus on detection engineering, downplay ML projects"
}
```

**Response 200**
```json
{
  "id": "uuid",
  "profile_id": "uuid",
  "job_id": "uuid",
  "saved_job_id": "uuid",
  "user_notes": "Focus on detection engineering...",
  "tailoring_rationale": "Reordered skills table to lead with Detection & Monitoring; swapped in SIEM-focused project bullets.",
  "has_pdf": true,
  "version": 1,
  "created_at": "2026-05-13T10:00:00Z"
}
```

**Errors** — `404` profile/saved-job not found, `500` AI or compile failure

---

### 8.2 Look up existing tailored resume

**Endpoint:** `GET /tailored-resumes`

**Query parameters**
- `profile_id` (required)
- `saved_job_id` (required)

**Response 200** — same shape as 8.1, or `404` if none exists

---

### 8.3 Download PDF

**Endpoint:** `GET /tailored-resumes/{resume_id}/pdf`

**Response 200** — `application/pdf` with `Content-Disposition: attachment; filename="resume_tailored_vN.pdf"`

**Errors** — `404` resume not found or PDF unavailable (compile failed)

---

### 8.4 Deferred endpoints (Phase 5D / 5E)

Not yet implemented — reserved for apply-orchestration and browser-extension layers:
- `POST /apply-plans` — create an apply plan from an approved draft
- `POST /apply-runs/{apply_run_id}/events` — extension-driven progress events
- `GET /jobs/resolve-by-url` — resolve an external job-page URL to a known `job_id`

---

## 8. Repo workflow impact

When API request or response shapes change:
- update this file
- update backend schemas and routers
- update frontend TypeScript types
- update `docs/TODO.md`
- package the change in a coherent Git branch/commit
