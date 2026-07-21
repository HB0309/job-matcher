export interface ProfileResponse {
  profile_id: string;
  headline: string | null;
  years_experience: number | null;
  skills: string[];
  preferred_titles: string[];
  preferred_level: string[];
  created_at?: string;
  updated_at?: string;
}

export interface ProfileUpdateRequest {
  preferred_titles?: string[];
  preferred_level?: string[];
}

export interface FailedTarget {
  target_id: string;
  connector: string;
  company_name: string;
  error: string;
}

export interface FetchJobsRequest {
  profile_id: string;
  connectors?: string[];
  target_ids?: string[];
  max_results_per_target?: number;
}

export interface FetchJobsResponse {
  fetch_run_id: string;
  profile_id: string;
  connectors: string[];
  target_count: number;
  total_jobs_fetched: number;
  total_jobs_normalized: number;
  total_jobs_matched: number;
  failed_targets: FailedTarget[];
  status: string;
}

export interface JobListItem {
  job_id: string;
  connector: string;
  source_target_id: string;
  company: string;
  title: string;
  location: string | null;
  url: string;
  posted_at: string | null;
  fetched_at: string | null;
  fetch_run_id: string | null;
  normalized_level: string | null;
  tags: string[];
  overall_score: number;
  title_score: number;
  skills_score: number;
  level_score: number;
  location_score: number;
}

export interface JobListResponse {
  profile_id: string;
  jobs: JobListItem[];
}

export interface ScoreBreakdown {
  overall: number;
  title: number;
  skills: number;
  level: number;
  location: number;
}

export interface ScoreExplanation {
  matched_skills: string[];
  missing_skills: string[];
  skill_count_job: number;
  skill_count_profile: number;
  level_explanation: string;
  location_explanation: string;
}

export interface JobDetail extends JobListItem {
  raw_description: string | null;
  scores: ScoreBreakdown;
  score_explanation?: ScoreExplanation | null;
}

export interface ConnectorSummary {
  name: string;
  display_name: string;
  enabled: boolean;
}

export interface SourcesResponse {
  sources: ConnectorSummary[];
}

export interface SourceTargetItem {
  id: string;
  connector: string;
  company_name: string;
  base_url: string;
  enabled: boolean;
  priority: number;
  last_success_at: string | null;
}

export interface SourceTargetsResponse {
  targets: SourceTargetItem[];
}

export interface SavedJob {
  id: string;
  profile_id: string;
  job_id: string;
  status: "saved" | "applied";
  saved_at: string;
  applied_at: string | null;
}

export interface ScheduledFetch {
  id: string;
  profile_id: string;
  connectors: string[] | null;
  interval_hours: number;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
}

export interface SavedJobWithDetails {
  id: string;
  profile_id: string;
  profile_headline: string | null;
  job_id: string;
  title: string;
  company: string;
  url: string | null;
  location: string | null;
  connector_name: string | null;
  status: "saved" | "applied";
  saved_at: string;
  applied_at: string | null;
}

// ---------------------------------------------------------------------------
// Apply Extension – application drafts and intent
// ---------------------------------------------------------------------------

export type DraftStatus =
  | "draft"
  | "review_pending"
  | "approved"
  | "stale"
  | "discarded";

export interface KeywordGap {
  matched: string[];
  missing: string[];
}

export interface ApplicationDraft {
  id: string;
  profile_id: string;
  saved_job_id: string;
  job_id: string;
  status: DraftStatus;
  fit_summary: string | null;
  keyword_gap_summary: KeywordGap | null;
  tailored_resume_json: Record<string, unknown> | null;
  tailored_resume_version: number;
  qa_answers_json: Record<string, unknown> | null;
  intent_snapshot_json: Record<string, unknown> | null;
  confidence_score: number;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
}

export interface ApplicationDraftCreate {
  profile_id: string;
  saved_job_id: string;
}

export interface ApplicationDraftPatch {
  status?: DraftStatus;
  qa_answers_json?: Record<string, unknown>;
  tailored_resume_json?: Record<string, unknown>;
  fit_summary?: string;
}

export type IntentKind =
  | "prepare_draft"
  | "review_draft"
  | "refresh_draft"
  | "start_apply"
  | "manual_only";

export type IntentSurface =
  | "apply_tab"
  | "job_detail"
  | "browser_extension"
  | "profile_edit"
  | "dashboard";

export interface RecommendedAction {
  type: string;
  label: string;
}

export interface IntentAssessRequest {
  surface?: IntentSurface;
  profile_id: string;
  saved_job_id?: string;
  job_id?: string;
  page_url?: string;
}

export interface IntentBatchRequest {
  surface?: IntentSurface;
  profile_id: string;
  saved_job_ids: string[];
}

export interface TailoredResumeCreate {
  profile_id: string;
  saved_job_id: string;
  user_notes?: string | null;
}

export interface TailoredResumeResponse {
  id: string;
  profile_id: string;
  job_id: string;
  saved_job_id: string;
  user_notes: string | null;
  tailoring_rationale: string | null;
  has_pdf: boolean;
  version: number;
  created_at: string;
}

export interface IntentAssessment {
  surface: IntentSurface;
  profile_id: string;
  saved_job_id: string | null;
  job_id?: string | null;
  intent: IntentKind;
  confidence: number;
  reasons: string[];
  recommended_action: RecommendedAction;
}
