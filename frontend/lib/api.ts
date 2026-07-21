import type {
  ApplicationDraft,
  ApplicationDraftCreate,
  ApplicationDraftPatch,
  FetchJobsRequest,
  FetchJobsResponse,
  IntentAssessment,
  IntentAssessRequest,
  IntentBatchRequest,
  JobDetail,
  JobListResponse,
  ProfileResponse,
  ProfileUpdateRequest,
  SavedJob,
  SavedJobWithDetails,
  ScheduledFetch,
  SourcesResponse,
  SourceTargetsResponse,
  TailoredResumeCreate,
  TailoredResumeResponse,
} from "@/types";

import { auth } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = auth.getToken();
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (res.status === 401 && !path.startsWith("/auth/") && token) {
    auth.clearToken();
    window.location.reload();
    throw new Error("Session expired — please log in again");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  listProfiles: () =>
    request<ProfileResponse[]>("/profiles"),

  createProfile: (formData: FormData) =>
    request<ProfileResponse>("/profiles", { method: "POST", body: formData }),

  getProfile: (profileId: string) =>
    request<ProfileResponse>(`/profiles/${profileId}`),

  deleteProfile: (profileId: string) =>
    request<void>(`/profiles/${profileId}`, { method: "DELETE" }),

  updateProfile: (profileId: string, patch: ProfileUpdateRequest) =>
    request<ProfileResponse>(`/profiles/${profileId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  fetchJobs: (req: FetchJobsRequest) =>
    request<FetchJobsResponse>("/fetch-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  listJobs: (params: {
    profile_id: string;
    min_score?: number;
    connector?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) qs.set(k, String(v));
    }
    return request<JobListResponse>(`/jobs?${qs}`);
  },

  getJob: (jobId: string, profileId: string) =>
    request<JobDetail>(`/jobs/${jobId}?profile_id=${profileId}`),

  getSources: () => request<SourcesResponse>("/sources"),

  getSourceTargets: (params?: { connector?: string }) => {
    const qs = new URLSearchParams();
    if (params?.connector) qs.set("connector", params.connector);
    return request<SourceTargetsResponse>(`/source-targets?${qs}`);
  },

  getSavedJobs: (profileId?: string) =>
    request<SavedJobWithDetails[]>(
      profileId ? `/saved-jobs?profile_id=${profileId}` : `/saved-jobs`
    ),

  saveJob: (body: { profile_id: string; job_id: string }) =>
    request<SavedJob>("/saved-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  updateSavedJob: (id: string, patch: { status: string }) =>
    request<SavedJob>(`/saved-jobs/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  deleteSavedJob: (id: string) =>
    request<void>(`/saved-jobs/${id}`, { method: "DELETE" }),

  getSchedules: (profileId: string) =>
    request<ScheduledFetch[]>(`/schedules?profile_id=${profileId}`),

  createSchedule: (body: { profile_id: string; connectors?: string[]; interval_hours: number }) =>
    request<ScheduledFetch>("/schedules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  updateSchedule: (id: string, patch: { enabled?: boolean; interval_hours?: number; connectors?: string[] }) =>
    request<ScheduledFetch>(`/schedules/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  deleteSchedule: (id: string) =>
    request<void>(`/schedules/${id}`, { method: "DELETE" }),

  // -------------------------------------------------------------------------
  // Apply Extension – application drafts and intent
  // -------------------------------------------------------------------------

  createDraft: (body: ApplicationDraftCreate) =>
    request<ApplicationDraft>("/application-drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getDraft: (draftId: string) =>
    request<ApplicationDraft>(`/application-drafts/${draftId}`),

  lookupDraft: (profileId: string, savedJobId: string) =>
    request<ApplicationDraft>(
      `/application-drafts?profile_id=${profileId}&saved_job_id=${savedJobId}`
    ),

  patchDraft: (draftId: string, patch: ApplicationDraftPatch) =>
    request<ApplicationDraft>(`/application-drafts/${draftId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  assessIntent: (req: IntentAssessRequest) =>
    request<IntentAssessment>("/intent/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  assessIntentBatch: (req: IntentBatchRequest) =>
    request<IntentAssessment[]>("/intent/assess-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  // -------------------------------------------------------------------------
  // Tailored resumes
  // -------------------------------------------------------------------------

  createTailoredResume: (body: TailoredResumeCreate) =>
    request<TailoredResumeResponse>("/tailored-resumes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  lookupTailoredResume: (profileId: string, savedJobId: string) =>
    request<TailoredResumeResponse>(
      `/tailored-resumes?profile_id=${profileId}&saved_job_id=${savedJobId}`
    ),

  triggerAutoApply: (draftId: string) =>
    request<{ status: string }>(`/application-drafts/${draftId}/apply`, { method: "POST" }),

  downloadPdfUrl: (resumeId: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("jm_token") : null;
    const base = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/tailored-resumes/${resumeId}/pdf`;
    return token ? `${base}?token=${encodeURIComponent(token)}` : base;
  },
};
