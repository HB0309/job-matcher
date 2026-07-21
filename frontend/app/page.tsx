"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { auth } from "@/lib/auth";
import type { FetchJobsResponse, JobListItem, ProfileResponse, SavedJobWithDetails } from "@/types";
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

export default function Home() {
  const [profiles, setProfiles] = useState<ProfileResponse[]>([]);
  const [activeProfile, setActiveProfile] = useState<ProfileResponse | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [lastRun, setLastRun] = useState<FetchJobsResponse | null>(null);
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [fetchLoading, setFetchLoading] = useState(false);
  const [allSavedJobs, setAllSavedJobs] = useState<SavedJobWithDetails[]>([]);
  const [activeTab, setActiveTab] = useState<"jobs" | "apply" | "applied">("jobs");

  // Profile-scoped subset — used only for Jobs tab checkboxes
  const profileSaved = allSavedJobs.filter((s) => s.profile_id === activeProfile?.profile_id);
  const savedMap = new Map(profileSaved.map((s) => [s.job_id, s]));
  const savedSet = new Set(profileSaved.filter((s) => s.status === "saved").map((s) => s.job_id));
  const appliedSet = new Set(profileSaved.filter((s) => s.status === "applied").map((s) => s.job_id));

  async function loadAllSavedJobs() {
    try {
      setAllSavedJobs(await api.getSavedJobs());
    } catch {
      setAllSavedJobs([]);
    }
  }

  async function toggleSave(jobId: string) {
    if (!activeProfile) return;
    const existing = savedMap.get(jobId);
    if (existing) {
      await api.deleteSavedJob(existing.id);
    } else {
      await api.saveJob({ profile_id: activeProfile.profile_id, job_id: jobId });
    }
    await loadAllSavedJobs();
  }

  // Jobs tab: mark applied by job_id (active profile only)
  async function markApplied(jobId: string) {
    const existing = savedMap.get(jobId);
    if (!existing) return;
    await api.updateSavedJob(existing.id, { status: "applied" });
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

  // Load all profiles and restore last-selected on mount
  useEffect(() => {
    if (!auth.isLoggedIn()) return;
    api.listProfiles().then((list) => {
      setProfiles(list);
      const savedId = localStorage.getItem(PROFILE_KEY);
      const match = list.find((p) => p.profile_id === savedId) ?? list[0] ?? null;
      if (match) {
        setActiveProfile(match);
        api
          .listJobs({ profile_id: match.profile_id, limit: 5000 })
          .then((r) => setJobs(r.jobs))
          .catch(() => {});
      }
      loadAllSavedJobs();
    });
  }, []);

  function selectProfile(p: ProfileResponse) {
    setActiveProfile(p);
    localStorage.setItem(PROFILE_KEY, p.profile_id);
    setLastRun(null);
    setJobs([]);
    setActiveTab("jobs");
    setShowUpload(false);
    api
      .listJobs({ profile_id: p.profile_id, limit: 5000 })
      .then((r) => setJobs(r.jobs))
      .catch(() => {});
  }

  async function handleDeleteProfile(p: ProfileResponse) {
    await api.deleteProfile(p.profile_id);
    const updated = profiles.filter((x) => x.profile_id !== p.profile_id);
    setProfiles(updated);
    if (activeProfile?.profile_id === p.profile_id) {
      const next = updated[0] ?? null;
      setActiveProfile(next);
      setJobs([]);
      setLastRun(null);
      if (next) {
        localStorage.setItem(PROFILE_KEY, next.profile_id);
        api.listJobs({ profile_id: next.profile_id, limit: 5000 }).then((r) => setJobs(r.jobs)).catch(() => {});
      } else {
        localStorage.removeItem(PROFILE_KEY);
      }
      setActiveTab("jobs");
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
    setProfiles((prev) => [p, ...prev]);
    selectProfile(p);
  }

  async function handleFetch(connectors: string[], maxResults: number) {
    if (!activeProfile) return;
    setFetchLoading(true);
    try {
      const run = await api.fetchJobs({
        profile_id: activeProfile.profile_id,
        connectors,
        max_results_per_target: maxResults,
      });
      setLastRun(run);
      const result = await api.listJobs({
        profile_id: activeProfile.profile_id,
        limit: 5000,
      });
      setJobs(result.jobs);
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

        {/* Step 2: Fetch jobs */}
        {activeProfile && (
          <section>
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              2 — Fetch Jobs
            </h2>
            <FetchPanel
              onFetch={handleFetch}
              loading={fetchLoading}
              lastRun={lastRun}
            />
            <div className="mt-3">
              <SchedulePanel profileId={activeProfile.profile_id} />
            </div>
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
                profileId={activeProfile!.profile_id}
                savedSet={savedSet}
                appliedSet={appliedSet}
                onToggleSave={toggleSave}
                latestRunId={lastRun?.fetch_run_id ?? null}
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
        {activeProfile && lastRun && jobs.length === 0 && !fetchLoading && (
          <p className="text-sm text-gray-400 text-center py-6">
            No matching jobs found. Try fetching again or adjusting your profile.
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
