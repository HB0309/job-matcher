# Job Matcher Apply Extension Plan

This document defines a detailed extension to the existing Job Matcher project. It is designed to plug into the current ATS-first architecture and add a discovery, drafting, intent assessment, and assisted application workflow on top of the existing profile, jobs, saved jobs, and apply components.[file:35][file:32][file:37][file:38]

## Goal

The extension adds a new layer that can:

- Detect user intent from existing product actions and current page context.
- Generate tailored application drafts from saved jobs and the selected profile.
- Connect those drafts directly to the current Apply tab and saved-jobs flow.
- Prepare automation-ready application plans for a future browser extension or semi-automated apply assistant.
- Keep all logic aligned with the current backend-first architecture instead of creating a disconnected side system.[file:35][file:34][file:38]

This extension should be implemented as a project feature set, not as a standalone app. The backend remains the source of truth, the frontend remains the main control surface, and the extension layer acts as an orchestration and intent-aware assistant on top of existing components.[file:35][file:32][file:37]

## Why this fits the current project

The current system already supports the core inputs needed for an application assistant:

- Profiles with uploaded resumes and parsed skills/preferences.[file:37][file:32]
- Matched jobs with normalized descriptions, tags, scores, and source connector metadata.[file:37][file:32]
- Saved jobs and Apply/Applied tracking in the frontend and backend.[file:34][file:35]
- A modular backend organized around worker-style agents and clear data flows.[file:32]
- A documented roadmap that explicitly leaves room for browser extension and automation work in later phases.[file:38]

Because of this, the extension should reuse existing job, profile, and saved-job records and introduce only the missing application-layer concepts instead of rebuilding discovery or profile logic from scratch.[file:34][file:35]

## Extension summary

The extension consists of five connected parts:

1. **Intent Assessment Layer**
2. **Application Drafting Layer**
3. **Apply Orchestration Layer**
4. **Frontend Integration Layer**
5. **Browser Extension / Automation Adapter Layer**

These layers should be implemented in that order. Each layer builds on the current project modules and APIs and keeps the future browser automation thin and controlled.

## Core product behavior

When a user opens the Apply tab or interacts with a saved job, the system should automatically assess what the user is likely trying to do and offer the next correct action. That means the product should not wait for the user to manually navigate a complex workflow if the system already has enough context to infer the likely intent.

Examples of inferred intent:

- User opens a saved job with no draft -> likely intent is **prepare application draft**.
- User opens a saved job with an existing draft that was never reviewed -> likely intent is **review application draft**.
- User opens a saved job with an approved draft -> likely intent is **start assisted apply**.
- User lands on a supported ATS page while logged into the project -> likely intent is **connect this page to the corresponding saved job and begin apply assistance**.
- User edits profile preferences or replaces resume -> likely intent is **refresh all outdated drafts tied to this profile**.

This is the core meaning of automatic intent assessment in this project: infer the next best action from user state, job state, draft state, and current page context.

## New domain objects

The extension should add new backend entities that connect naturally to existing `profiles`, `jobpostings`, `jobmatches`, and `savedjobs` records.[file:34][file:37]

### 1. ApplicationDraft

Purpose: store the job-specific application package generated for one profile and one saved job.

Suggested fields:

- `id`
- `profile_id`
- `job_id`
- `saved_job_id`
- `status` (`draft`, `review_pending`, `approved`, `stale`, `discarded`)
- `fit_summary`
- `keyword_gap_summary`
- `tailored_resume_json`
- `tailored_resume_version`
- `tailored_resume_file_path` (optional in v1)
- `qa_answers_json`
- `intent_snapshot_json`
- `confidence_score`
- `created_at`
- `updated_at`
- `approved_at`

### 2. ApplyRun

Purpose: track a real apply attempt and connect backend state to future extension execution.

Suggested fields:

- `id`
- `profile_id`
- `job_id`
- `saved_job_id`
- `application_draft_id`
- `mode` (`manual`, `semi_auto`, `auto`)
- `status` (`pending`, `running`, `paused`, `submitted`, `failed`, `abandoned`)
- `step_log_json`
- `error_log_json`
- `result_summary`
- `started_at`
- `completed_at`

### 3. IntentSignal

Purpose: store why the system inferred a user intent, so product behavior remains explainable.

Suggested fields:

- `id`
- `profile_id`
- `job_id` (nullable)
- `saved_job_id` (nullable)
- `surface` (`apply_tab`, `job_detail`, `browser_extension`, `profile_edit`, `dashboard`)
- `detected_intent` (`prepare_draft`, `review_draft`, `refresh_draft`, `start_apply`, `resume_apply`, `mark_applied`, `manual_only`)
- `signals_json`
- `confidence_score`
- `created_at`

This table can be optional in the first implementation, but the model is useful because it keeps intent assessment inspectable and debuggable.

## How intent assessment should work

Intent assessment should be deterministic first and model-assisted second. The initial version should rely on state rules derived from current records rather than full LLM reasoning. That fits the current project style, which is already modular and rule-driven in resume parsing, matching, filtering, and scoring.[file:32][file:34]

### Intent inputs

The intent engine should consider:

- Current route/page in frontend.
- Whether the job is saved.
- Whether an ApplicationDraft exists.
- Draft status.
- Whether the profile resume changed since draft creation.
- Whether the job posting changed or was refreshed.
- Whether the user is on an external ATS page recognized by the browser adapter.
- Whether an ApplyRun exists and is incomplete.
- Whether the current ATS page URL matches a known `jobposting.url`.

### Initial intent rules

| Context | Conditions | Inferred intent | UX action |
|---|---|---|---|
| Apply tab row opened | Saved job exists, no draft | `prepare_draft` | Show “Generate application draft” primary action |
| Apply tab row opened | Draft exists, status `review_pending` | `review_draft` | Open review drawer/panel |
| Apply tab row opened | Draft exists, status `approved`, no ApplyRun | `start_apply` | Show “Start assisted apply” |
| Apply tab row opened | ApplyRun exists, status `paused` | `resume_apply` | Show “Resume application” |
| Profile updated | Resume timestamp newer than draft timestamp | `refresh_draft` | Mark drafts stale, offer regenerate |
| External ATS page detected | URL matches known job and approved draft exists | `start_apply` | Show extension CTA to assist |
| External ATS page detected | URL matches known job but no draft exists | `prepare_draft` | Prompt to generate draft from project |
| Job already applied | Saved job status `applied` | `manual_only` | Disable automation and show applied state |

### Intent engine implementation

Create a new backend module such as:

- `workers/intent_engine.py`

Responsibility:

- Evaluate current state and return a structured `IntentAssessment` response.
- Explain why the intent was inferred.
- Feed both frontend and future browser extension.

Suggested response DTO:

```json
{
  "surface": "apply_tab",
  "profileId": "...",
  "jobId": "...",
  "savedJobId": "...",
  "intent": "prepare_draft",
  "confidence": 0.96,
  "reasons": [
    "job is saved",
    "no application draft exists",
    "job is not marked applied"
  ],
  "recommendedAction": {
    "type": "create_draft",
    "label": "Generate application draft"
  }
}
```

## Application drafting layer

This layer creates job-specific application materials from the current profile and job data.

### Responsibilities

- Read selected profile and its base resume.
- Read normalized job posting plus raw description text.[file:37]
- Build a job-specific fit summary.
- Identify keyword gaps and supported ATS keywords.
- Generate tailored resume content.
- Prepare reusable answers for expected application questions.
- Store outputs in `ApplicationDraft`.

### New backend module

Suggested file:

- `workers/application_drafter.py`

### Inputs

- `profile_id`
- `job_id`
- `saved_job_id`
- Base profile record
- Structured resume representation
- Job posting detail from existing jobs API / DB record.[file:37]

### Outputs

- `fit_summary`
- `keyword_gap_summary`
- `tailored_resume_json`
- `qa_answers_json`
- `confidence_score`
- `status=review_pending`

### Draft generation strategy

Use a hybrid approach:

1. Use deterministic extraction from current profile data first.
2. Add structured resume parsing for experiences, bullets, projects, certifications.
3. Match job tags and description against available resume evidence.
4. Generate tailored bullets only from existing truthful experience.
5. Generate answer skeletons for common application prompts.

### Q&A categories

- Personal info
- Work authorization
- Sponsorship
- Location / relocation
- Salary expectations
- Years of experience in named tools
- Why this role
- Why this company
- Security/compliance-related disclosures

Deterministic answers should be separated from free-text drafted answers so the review UI can make confidence differences obvious.

## Apply orchestration layer

This layer prepares the backend state and instructions that the future browser extension will execute.

### Purpose

The backend should decide **what** needs to be done. The browser layer should mainly decide **how** to do it on a specific page.

### New backend module

Suggested file:

- `workers/apply_orchestrator.py`

### Responsibilities

- Validate that the saved job is eligible for apply assistance.
- Require an approved or explicitly allowed draft.
- Create an `ApplyRun`.
- Produce an `ApplyPlan` payload.
- Expose progress and failure hooks for the extension.

### ApplyPlan concept

Example shape:

```json
{
  "applyRunId": "...",
  "jobId": "...",
  "profileId": "...",
  "connector": "greenhouse",
  "jobUrl": "https://boards.greenhouse.io/...",
  "mode": "semi_auto",
  "resumeVariant": "tailored",
  "questionAnswers": {
    "work_authorization": "Authorized to work in the United States.",
    "sponsorship": "No sponsorship required.",
    "location": "Open to roles in Virginia, DC, Maryland, and remote."
  },
  "steps": [
    { "type": "navigate", "value": "job_url" },
    { "type": "detect_form" },
    { "type": "upload_resume", "value": "tailored_resume_file" },
    { "type": "fill_known_fields" },
    { "type": "pause_for_review" },
    { "type": "submit_if_confirmed" }
  ]
}
```

V1 does not need a universal perfect step planner. It needs a stable API contract that later browser automation can consume incrementally.

## Frontend integration into current components

This extension should connect directly into the current Next.js surfaces instead of creating a separate frontend flow.[file:35][file:34]

### 1. Apply tab integration

Current Apply tab already shows saved jobs across profiles.[file:34]

Extend each Apply row with:

- Intent chip: “Draft needed”, “Review draft”, “Ready to apply”, “Resume apply”, “Applied”.
- Draft status chip.
- Primary CTA based on `IntentAssessment`.
- Secondary CTA: open job detail, edit draft, regenerate draft.

Suggested flow:

- User opens Apply tab.
- Frontend loads saved jobs as it already does.[file:34]
- Frontend also calls intent endpoint for each visible row or via batch endpoint.
- UI sorts actionable rows to the top.
- Primary action label changes based on inferred intent.

### 2. Job detail integration

Add a right-side panel or modal with:

- Fit summary
- Keyword gap summary
- Tailored resume preview
- Q&A preview
- Draft approval controls
- Regenerate button

### 3. Profile page integration

When profile changes:

- detect if resume file changed,
- mark related drafts `stale`,
- surface a “Regenerate N outdated drafts” banner.

### 4. Dashboard notifications

Optional but useful:

- “12 saved jobs need drafts”
- “4 approved drafts are ready for apply assistance”
- “2 applications were paused and can be resumed”

## Browser extension / automation adapter

This part should remain deliberately thin. The project docs already position browser extension work as a later phase, so the best architecture is to build the backend contract first and only then add the extension execution shell.[file:38]

### Browser extension responsibilities

- Detect supported ATS/job pages.
- Read current page URL and metadata.
- Ask backend to resolve that URL to a known job.
- Request `IntentAssessment` and `ApplyPlan`.
- Fill forms using approved backend-provided answers.
- Report progress and status back to backend.

### Browser extension should not own

- Resume tailoring logic
- Keyword gap logic
- Profile truth source
- State machine for draft approval
- Job matching logic
- Final persistence of application state

Those all belong in the current project backend.

## API additions

The extension requires API contracts that fit the current style of the documented FastAPI backend.[file:37]

### New endpoints

#### `POST /jobs/{job_id}/application-drafts`

Create or return a draft for the selected saved job/profile.

Request:

```json
{
  "profileId": "...",
  "savedJobId": "..."
}
```

#### `GET /application-drafts/{draft_id}`

Return full draft detail.

#### `PATCH /application-drafts/{draft_id}`

Approve, discard, or edit parts of the draft.

#### `POST /intent/assess`

Assess current user intent from project state.

Request:

```json
{
  "surface": "apply_tab",
  "profileId": "...",
  "jobId": "...",
  "savedJobId": "...",
  "pageUrl": null
}
```

#### `POST /intent/assess-batch`

Return intent for multiple saved jobs to support Apply tab efficiency.

#### `POST /apply-plans`

Create an apply plan for a saved job with an approved draft.

#### `POST /apply-runs/{apply_run_id}/events`

Allow browser extension to stream apply progress.

#### `GET /jobs/resolve-by-url`

Resolve external ATS page to a known `job_id` / `saved_job_id`.

These endpoints should be added to API docs and frontend types in the same change set, consistent with the existing repo workflow rules.[file:37][file:34]

## Component-level connection plan

This section maps the extension directly to the current project components.

| Existing project component | Current role | Extension addition |
|---|---|---|
| `profiles` flow | Stores resume, titles, level, parsed skills | Add structured resume representation and stale-draft triggers |
| Resume parser agent | Extracts headline, years, skills | Extend into resume structuring for bullet-level tailoring |
| `jobs` / `jobpostings` | Stores normalized jobs and descriptions | Becomes source data for draft generation and apply planning |
| Matcher | Computes score and relevance | Feed fit summary and prioritization for drafting |
| `savedjobs` | Tracks Apply/Applied state | Becomes anchor record for ApplicationDraft and ApplyRun |
| Apply tab | Displays jobs to work through | Becomes main intent-aware work queue |
| Applied tab | Tracks completed applications | Also displays ApplyRun summary / result metadata |
| FastAPI worker modules | Existing orchestration pattern | Add `intent_engine`, `application_drafter`, `apply_orchestrator` |
| Browser extension phase | Planned future phase | Consume backend intent + apply plan instead of owning logic |

## State machine

The extension should introduce an explicit state machine so behavior stays predictable.

### Saved job + draft state

```text
saved -> draft_pending -> review_pending -> approved -> apply_ready -> apply_running -> applied
                              |                |             |
                              |                |             -> paused
                              |                -> stale
                              -> discarded
```

### Rules

- A saved job cannot enter `apply_ready` without a draft.
- A stale draft cannot be used for auto-apply without regenerate or override.
- An applied saved job cannot receive a new active ApplyRun unless explicitly reopened.
- Profile updates can push existing drafts into `stale`.

## Suggested repository placement

Based on the existing architecture and docs, these additions should be placed in the current backend/frontend layout rather than in a separate repo.[file:32][file:35]

### Backend

Suggested additions:

- `app/workers/intent_engine.py`
- `app/workers/application_drafter.py`
- `app/workers/apply_orchestrator.py`
- `app/models/application_draft.py`
- `app/models/apply_run.py`
- `app/routers/application_drafts.py`
- `app/routers/intent.py`
- `app/routers/apply_runs.py`
- migration for new tables and profile extensions

### Frontend

Suggested additions:

- `frontend/components/apply/IntentChip.tsx`
- `frontend/components/apply/ApplicationDraftPanel.tsx`
- `frontend/components/apply/ApplyActionButton.tsx`
- `frontend/lib/api/applicationDrafts.ts`
- `frontend/lib/api/intent.ts`
- Apply tab row enhancement
- Job detail drawer enhancement

### Browser extension later

Suggested separate package only when ready:

- `packages/browser-extension/`

This package should depend on backend APIs and not duplicate backend business logic.

## Detailed implementation phases

### Phase A: Data model and backend contract

Tasks:

- Add `application_drafts` table.
- Add `apply_runs` table.
- Extend profile with structured resume storage.
- Add `intent` and `draft` schemas.
- Add migration scripts.
- Update docs and TODO tracker in the same branch.[file:34][file:38]

Exit criteria:

- Backend can store drafts and apply runs.
- Intent endpoint can classify a saved job into a next action.

### Phase B: Drafting engine

Tasks:

- Build structured resume extractor.
- Build keyword-gap and fit-summary generator.
- Build resume tailoring pipeline.
- Build Q&A skeleton generator.
- Persist drafts and stale detection.

Exit criteria:

- For any saved job, backend can generate a reviewable draft.

### Phase C: Frontend integration

Tasks:

- Add intent-aware CTA in Apply tab.
- Add review panel.
- Add draft status indicators.
- Add stale-draft warnings.
- Add regenerate workflow.

Exit criteria:

- Apply tab becomes a real application work queue.

### Phase D: Apply orchestration API

Tasks:

- Implement ApplyPlan generation.
- Create ApplyRun lifecycle endpoints.
- Support at least one connector-specific assisted-apply target in design, even if execution remains manual.

Exit criteria:

- Backend can produce automation-ready instructions for approved drafts.

### Phase E: Browser extension v1

Tasks:

- Detect supported ATS pages.
- Resolve job by URL.
- Fetch intent and apply plan.
- Fill easy/deterministic fields.
- Pause before submit.
- Report result back to backend.

Exit criteria:

- Semi-automated apply works for at least one ATS flow end-to-end.

## Technical principles

### 1. Backend-first truth

The backend should remain the source of truth for profile data, draft data, job identity, and apply state. This is consistent with the current architecture and avoids logic split across frontend and extension.[file:32][file:37]

### 2. Rule-based intent first

The first version of intent assessment should be deterministic and inspectable. Use model assistance only where text generation is needed, not for deciding core workflow state.

### 3. Human-in-the-loop by default

The extension should optimize speed and reduce manual effort, but it should not jump straight to blind mass submission. Review checkpoints should exist at the draft stage and at least near final submit.

### 4. Tight integration with current Apply flow

The Apply tab should become the center of application operations. The extension is not a replacement for the project UI; it is an execution assistant attached to it.

### 5. Docs and code stay synchronized

The project already emphasizes synchronized docs, API contracts, TODO tracking, and coherent branch-based changes.[file:34][file:37][file:39][file:40]

Every change in this extension should update:

- architecture docs if module responsibilities change,
- API contracts if request/response shapes change,
- backlog phases if roadmap changes,
- TODO tracker when tasks move.

## Recommended first slice

The first usable slice should be intentionally narrow:

- Add `ApplicationDraft` model and endpoints.
- Add `IntentAssessment` endpoint.
- Extend Apply tab with intent-aware CTAs.
- Support “Generate draft” and “Review draft”.
- Do not implement browser automation yet.

That gives immediate value inside the current app and creates the correct foundation for later assisted-apply work.

## Acceptance criteria

This extension is successful when:

- A saved job automatically shows the most likely next action in the Apply tab.
- The system can generate a tailored application draft from the selected profile and job.
- Profile changes automatically mark outdated drafts as stale.
- The project exposes backend contracts that a future browser extension can consume cleanly.
- Apply-related behavior is traceable through explicit state and intent assessment instead of hidden UI heuristics.
- The extension feels like a native evolution of the current Job Matcher product rather than a bolt-on script.

## Final recommendation

Treat this extension as an **Application Intelligence Layer** inside the existing Job Matcher architecture. The key design choice is to centralize intent assessment, drafting, and apply orchestration in the backend and attach them directly to `profiles`, `jobs`, `savedjobs`, and the Apply tab. The browser extension should be the last layer added, and it should consume backend decisions rather than redefine them.

This approach fits the current ATS-first system design, respects the existing modular worker pattern, connects cleanly to present components, and creates a path toward assisted or semi-automated application workflows without breaking the current project structure.[file:35][file:32][file:37][file:38]
