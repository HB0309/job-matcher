"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { auth } from "@/lib/auth";
import type {
  CombinedJobItem,
  FetchJobsResponse,
  JobListItem,
  JobProfileMatch,
  ProfileResponse,
  SavedJobWithDetails,
} from "@/types";
import AuthGate from "@/components/AuthGate";
import FetchPanel from "@/components/FetchPanel";
import JobsList from "@/components/JobsList";
import ApplyList from "@/components/ApplyList";
import AppliedList from "@/components/AppliedList";
import ProfileCard from "@/components/ProfileCard";
import ProfileUpload from "@/components/ProfileUpload";
import SchedulePanel from "@/components/SchedulePanel";
import SourcesPanel from "@/components/SourcesPanel";

const PROFILE_KEY = "jm_profile_id";

// Merges per-profile job lists into one row per job_id, tagged with every
// profile that matched it. The primary match (matches[0], highest score)
// drives the shared score/filter columns so JobsList's existing sort/filter
// logic keeps working unchanged.
function mergeJobsAcrossProfiles(
  entries: { profile: ProfileResponse; jobs: JobListItem[] }[]
): CombinedJobItem[] {
  const byId = new Map<string, CombinedJobItem>();
  for (const { profile, jobs } of entries) {
    for (const j of jobs) {
      const match: JobProfileMatch = {
        profile_id: profile.profile_id,
        profile_headline: profile.headline,
        profile_titles: profile.preferred_titles,
        overall_score: j.overall_score,
        title_score: j.title_score,
        skills_score: j.skills_score,
        level_score: j.level_score,
        location_score: j.location_score,
      };
      const existing = byId.get(j.job_id);
      if (existing) {
        existing.matches.push(match);
      } else {
        byId.set(j.job_id, { ...j, matches: [match] });
      }
    }
  }
  const combined = Array.from(byId.values());
  for (const c of combined) {
    c.matches.sort((a, b) => b.overall_score - a.overall_score);
    const primary = c.matches[0];
    c.overall_score = primary.overall_score;
    c.title_score = primary.title_score;
    c.skills_score = primary.skills_score;
    c.level_score = primary.level_score;
    c.location_score = primary.location_score;
  }
  return combined;
}

export default function Home() {
  const [profiles, setProfiles] = useState<ProfileResponse[]>([]);
  const [activeProfile, setActiveProfile] = useState<ProfileResponse | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [lastRuns, setLastRuns] = useState<FetchJobsResponse[]>([]);
  const [jobs, setJobs] = useState<CombinedJobItem[]>([]);
  const [fetchLoading, setFetchLoading] = useState(false);
  const [allSavedJobs, setAllSavedJobs] = useState<SavedJobWithDetails[]>([]);
  const [activeTab, setActiveTab] = useState<"jobs" | "apply" | "applied">("jobs");

  // Keyed by `${profile_id}:${job_id}` since a job row can carry matches
  // from several profiles — save/apply state must track which profile's
  // match a given save belongs to, not just the job_id.
  const savedMap = new Map(allSavedJobs.map((s) => [`${s.profile_id}:${s.job_id}`, s]));
  const savedSet = new Set(
    allSavedJobs.filter((s) => s.status === "saved").map((s) => `${s.profile_id}:${s.job_id}`)
  );
  const appliedSet = new Set(
    allSavedJobs.filter((s) => s.status === "applied").map((s) => `${s.profile_id}:${s.job_id}`)
  );

  async function loadAllSavedJobs() {
    try {
      setAllSavedJobs(await api.getSavedJobs());
    } catch {
      setAllSavedJobs([]);
    }
  }

  async function loadCombinedJobs(list: ProfileResponse[]) {
    const entries = await Promise.all(
      list.map((profile) =>
        api
          .listJobs({ profile_id: profile.profile_id, limit: 5000 })
          .then((r) => ({ profile, jobs: r.jobs }))
          .catch(() => ({ profile, jobs: [] as JobListItem[] }))
      )
    );
    setJobs(mergeJobsAcrossProfiles(entries));
  }

  // Toggle save under a specific profile's match on this job row (usually
  // the row's primary/highest-scoring profile).
  async function toggleSave(jobId: string, profileId: string) {
    const existing = savedMap.get(`${profileId}:${jobId}`);
    if (existing) {
      await api.deleteSavedJob(existing.id);
    } else {
      await api.saveJob({ profile_id: profileId, job_id: jobId });
    }
    await loadAllSavedJobs();
  }

  // Apply/Applied tabs: act on a specific SavedJob record ID directly
  async function markAppliedById(recordId: string) {
    await api.updateSavedJob(recordId, { status: "applied" });
    await loadAllSavedJobs();
  }

  async function undoAppliedById(recordId: string) {
    await api.updateSavedJob(recordId, { status: "saved" });
    await loadAllSavedJobs();
  }

  async function removeFromApply(recordId: string) {
    await api.deleteSavedJob(recordId);
    await loadAllSavedJobs();
  }

  // Load all profiles and their combined job matches on mount
  useEffect(() => {
    if (!auth.isLoggedIn()) return;
    api.listProfiles().then((list) => {
      setProfiles(list);
      const savedId = localStorage.getItem(PROFILE_KEY);
      const match = list.find((p) => p.profile_id === savedId) ?? list[0] ?? null;
      setActiveProfile(match);
      if (list.length > 0) {
        loadCombinedJobs(list);
      }
      loadAllSavedJobs();
    });
  }, []);

  // Selects which profile is "active" for editing / the schedule panel —
  // the combined Jobs list itself is not profile-scoped.
  function selectProfile(p: ProfileResponse) {
    setActiveProfile(p);
    localStorage.setItem(PROFILE_KEY, p.profile_id);
    setShowUpload(false);
  }

  async function handleDeleteProfile(p: ProfileResponse) {
    await api.deleteProfile(p.profile_id);
    const updated = profiles.filter((x) => x.profile_id !== p.profile_id);
    setProfiles(updated);
    if (activeProfile?.profile_id === p.profile_id) {
      const next = updated[0] ?? null;
      setActiveProfile(next);
      if (next) {
        localStorage.setItem(PROFILE_KEY, next.profile_id);
      } else {
        localStorage.removeItem(PROFILE_KEY);
      }
    }
    if (updated.length > 0) {
      loadCombinedJobs(updated);
    } else {
      setJobs([]);
    }
    loadAllSavedJobs();
  }

  function handleProfileUpdated(updated: ProfileResponse) {
    setProfiles((prev) => prev.map((p) => p.profile_id === updated.profile_id ? updated : p));
    if (activeProfile?.profile_id === updated.profile_id) {
      setActiveProfile(updated);
    }
  }

  function handleProfileCreated(p: ProfileResponse) {
    setProfiles((prev) => {
      const next = [p, ...prev];
      loadCombinedJobs(next);
      return next;
    });
    selectProfile(p);
  }

  async function handleFetch(connectors: string[], maxResults: number) {
    if (profiles.length === 0) return;
    setFetchLoading(true);
    try {
      const runs = await api.fetchAllJobs(connectors, maxResults);
      setLastRuns(runs);
      await loadCombinedJobs(profiles);
    } finally {
      setFetchLoading(false);
    }
  }

  const noProfiles = profiles.length === 0 && !showUpload;

  return (
    <AuthGate>
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Job Matcher</h1>
          <p className="text-xs text-gray-400 mt-0.5">Aggregator-first job matching</p>
        </div>
        <button
          onClick={() => { auth.clearToken(); window.location.reload(); }}
          className="text-xs text-gray-400 hover:text-gray-600"
        >
          Sign out
        </button>
      </header>

      <main className="w-full max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-10 py-8 space-y-8">

        {/* Step 1: Profiles */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              1 — Profile
            </h2>
            <button
              onClick={() => setShowUpload((v) => !v)}
              className="text-xs text-blue-600 hover:text-blue-800"
            >
              {showUpload ? "Cancel" : "+ Add resume"}
            </button>
          </div>

          {/* Upload form */}
          {(showUpload || noProfiles) && (
            <div className="mb-4">
              <ProfileUpload onCreated={handleProfileCreated} />
            </div>
          )}

          {/* Profile switcher */}
          {profiles.length > 0 && !showUpload && (
            <div className="space-y-2">
              {profiles.map((p) => (
                <div
                  key={p.profile_id}
                  onClick={() => selectProfile(p)}
                  className={`cursor-pointer rounded-lg border transition-colors ${
                    activeProfile?.profile_id === p.profile_id
                      ? "border-blue-400 ring-1 ring-blue-400"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <ProfileCard
                    profile={p}
                    onReset={() => setShowUpload(true)}
                    onDelete={() => handleDeleteProfile(p)}
                    onUpdated={handleProfileUpdated}
                  />
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Step 2: Fetch jobs — runs for every profile in one click */}
        {profiles.length > 0 && (
          <section>
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              2 — Fetch Jobs
            </h2>
            <FetchPanel
              onFetch={handleFetch}
              loading={fetchLoading}
              lastRuns={lastRuns}
              profiles={profiles}
            />
            {activeProfile && (
              <div className="mt-3">
                <SchedulePanel profileId={activeProfile.profile_id} />
              </div>
            )}
          </section>
        )}

        {/* Jobs / Apply / Applied tabs */}
        {(jobs.length > 0 || allSavedJobs.length > 0) && (
          <section>
            {/* Tab bar */}
            <div className="flex border-b border-gray-200 mb-4">
              {(["jobs", "apply", "applied"] as const).map((tab) => {
                const applyCount = allSavedJobs.filter((s) => s.status === "saved").length;
                const appliedCount = allSavedJobs.filter((s) => s.status === "applied").length;
                const label =
                  tab === "jobs"
                    ? `Jobs (${jobs.length})`
                    : tab === "apply"
                    ? `Apply (${applyCount})`
                    : `Applied (${appliedCount})`;
                return (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      activeTab === tab
                        ? "text-blue-600 border-b-2 border-blue-500 -mb-px"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            {activeTab === "jobs" && (
              <JobsList
                jobs={jobs}
                savedSet={savedSet}
                appliedSet={appliedSet}
                onToggleSave={toggleSave}
                latestRunIds={lastRuns.map((r) => r.fetch_run_id)}
              />
            )}
            {activeTab === "apply" && (
              <ApplyList
                savedJobs={allSavedJobs.filter((j) => j.status === "saved")}
                onRemove={removeFromApply}
                onMarkApplied={markAppliedById}
              />
            )}
            {activeTab === "applied" && (
              <AppliedList
                savedJobs={allSavedJobs.filter((j) => j.status === "applied")}
                onUndo={undoAppliedById}
              />
            )}
          </section>
        )}

        {/* Empty state after fetch */}
        {lastRuns.length > 0 && jobs.length === 0 && !fetchLoading && (
          <p className="text-sm text-gray-400 text-center py-6">
            No matching jobs found. Try fetching again or adjusting your profiles.
          </p>
        )}

        {/* Sources panel */}
        <section>
          <SourcesPanel />
        </section>
      </main>
    </div>
    </AuthGate>
  );
}
