from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

NormalizedLevel = Literal["new_grad", "entry", "junior", "mid", "senior", "staff", "principal"]


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

class ProfileUpdateRequest(BaseModel):
    preferred_titles: list[str] | None = None
    preferred_level: list[str] | None = None


class ProfileResponse(BaseModel):
    profile_id: str
    headline: str | None
    years_experience: int | None
    skills: list[str]
    preferred_titles: list[str]
    preferred_level: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Fetch jobs
# ---------------------------------------------------------------------------

class FetchJobsRequest(BaseModel):
    profile_id: str
    connectors: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    max_results_per_target: int | None = None


class FetchAllJobsRequest(BaseModel):
    connectors: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    max_results_per_target: int | None = None


class FailedTarget(BaseModel):
    target_id: str
    connector: str
    company_name: str
    error: str


class FetchJobsResponse(BaseModel):
    fetch_run_id: str
    profile_id: str
    connectors: list[str]
    target_count: int
    total_jobs_fetched: int
    total_jobs_normalized: int
    total_jobs_matched: int
    failed_targets: list[FailedTarget]
    status: str


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class JobListItem(BaseModel):
    job_id: str
    connector: str
    source_target_id: str
    company: str
    title: str
    location: str | None
    url: str
    posted_at: datetime | None
    fetched_at: datetime | None  # when WE matched it (JobMatch.created_at)
    fetch_run_id: str | None
    normalized_level: str | None
    tags: list[str]
    overall_score: float
    title_score: float
    skills_score: float
    level_score: float
    location_score: float

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    profile_id: str
    jobs: list[JobListItem]


class ScoreBreakdown(BaseModel):
    overall: float
    title: float
    skills: float
    level: float
    location: float


class ScoreExplanation(BaseModel):
    matched_skills: list[str]
    missing_skills: list[str]
    skill_count_job: int
    skill_count_profile: int
    level_explanation: str
    location_explanation: str


class JobDetail(BaseModel):
    job_id: str
    connector: str
    source_target_id: str
    company: str
    title: str
    location: str | None
    url: str
    posted_at: datetime | None
    raw_description: str | None
    normalized_level: str | None
    tags: list[str]
    scores: ScoreBreakdown
    score_explanation: ScoreExplanation | None = None
    # Populated only for postings the Stage 3 agent actually scored (see
    # docs/03-agents-flows.md §3.2b) — "[agentic] score=0.NN — <rationale>".
    # None for postings the agentic funnel never reached or that ran before
    # this feature existed.
    agentic_explanation: str | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Sources and targets
# ---------------------------------------------------------------------------

class ConnectorSummary(BaseModel):
    name: str
    display_name: str
    enabled: bool

    model_config = {"from_attributes": True}


class SourcesResponse(BaseModel):
    sources: list[ConnectorSummary]


class SourceTargetItem(BaseModel):
    id: str
    connector: str
    company_name: str
    base_url: str
    enabled: bool
    priority: int
    last_success_at: datetime | None

    model_config = {"from_attributes": True}


class SourceTargetsResponse(BaseModel):
    targets: list[SourceTargetItem]


class SourceTargetCreateRequest(BaseModel):
    connector: str
    company_name: str
    company_key: str | None = None
    base_url: str
    enabled: bool = True
    priority: int = 100
    config: dict = Field(default_factory=dict)


class SourceTargetCreateResponse(BaseModel):
    id: str
    connector: str
    company_name: str
    enabled: bool


# ---------------------------------------------------------------------------
# Saved jobs
# ---------------------------------------------------------------------------

class SavedJobCreate(BaseModel):
    profile_id: str
    job_id: str


class SavedJobUpdate(BaseModel):
    status: str  # "saved" | "applied"


class SavedJobResponse(BaseModel):
    id: str
    profile_id: str
    job_id: str
    status: str
    saved_at: datetime
    applied_at: datetime | None

    model_config = {"from_attributes": True}


class SavedJobWithDetails(BaseModel):
    id: str
    profile_id: str
    profile_headline: str | None
    job_id: str
    title: str
    company: str
    url: str | None
    location: str | None
    connector_name: str | None
    status: str
    saved_at: datetime
    applied_at: datetime | None


# ---------------------------------------------------------------------------
# Scheduled fetches
# ---------------------------------------------------------------------------

class ScheduledFetchCreate(BaseModel):
    profile_id: str
    connectors: list[str] | None = None
    interval_hours: int = 24


class ScheduledFetchUpdate(BaseModel):
    connectors: list[str] | None = None
    interval_hours: int | None = None
    enabled: bool | None = None


class ScheduledFetchResponse(BaseModel):
    id: str
    profile_id: str
    connectors: list[str] | None
    interval_hours: int
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Application drafts
# ---------------------------------------------------------------------------

DraftStatus = Literal["draft", "review_pending", "approved", "stale", "discarded"]


class KeywordGap(BaseModel):
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ApplicationDraftCreate(BaseModel):
    profile_id: str
    saved_job_id: str


class ApplicationDraftPatch(BaseModel):
    status: DraftStatus | None = None
    qa_answers_json: dict | None = None
    tailored_resume_json: dict | None = None
    fit_summary: str | None = None


class ApplicationDraftResponse(BaseModel):
    id: str
    profile_id: str
    saved_job_id: str
    job_id: str
    status: DraftStatus
    fit_summary: str | None
    keyword_gap_summary: KeywordGap | None
    tailored_resume_json: dict | None
    tailored_resume_version: int
    qa_answers_json: dict | None
    intent_snapshot_json: dict | None
    confidence_score: float
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Intent assessment
# ---------------------------------------------------------------------------

IntentKind = Literal[
    "prepare_draft", "review_draft", "refresh_draft", "start_apply", "manual_only"
]
IntentSurface = Literal["apply_tab", "job_detail", "browser_extension", "profile_edit", "dashboard"]


class RecommendedAction(BaseModel):
    type: str
    label: str


class IntentAssessRequest(BaseModel):
    surface: IntentSurface = "apply_tab"
    profile_id: str
    saved_job_id: str | None = None
    job_id: str | None = None
    page_url: str | None = None


class IntentBatchRequest(BaseModel):
    surface: IntentSurface = "apply_tab"
    profile_id: str
    saved_job_ids: list[str] = Field(default_factory=list)


class IntentAssessmentResponse(BaseModel):
    surface: IntentSurface
    profile_id: str
    saved_job_id: str | None
    job_id: str | None = None
    intent: IntentKind
    confidence: float
    reasons: list[str]
    recommended_action: RecommendedAction


# ---------------------------------------------------------------------------
# Tailored resumes
# ---------------------------------------------------------------------------

class TailoredResumeCreate(BaseModel):
    profile_id: str
    saved_job_id: str
    user_notes: str | None = None


class TailoredResumeResponse(BaseModel):
    id: str
    profile_id: str
    job_id: str
    saved_job_id: str
    user_notes: str | None
    tailoring_rationale: str | None
    has_pdf: bool
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Tasks (fetch run status)
# ---------------------------------------------------------------------------

class FetchRunTargetStatus(BaseModel):
    target_id: str
    status: str
    jobs_fetched: int
    error_message: str | None

    model_config = {"from_attributes": True}


class FetchRunStatusResponse(BaseModel):
    fetch_run_id: str
    profile_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    total_jobs_fetched: int
    total_jobs_normalized: int
    total_jobs_matched: int
    error_summary: str | None
    targets: list[FetchRunTargetStatus]

    model_config = {"from_attributes": True}
