"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { IntentAssessment, IntentKind, SavedJobWithDetails } from "@/types";

import ApplicationDraftPanel from "./ApplicationDraftPanel";
import IntentChip from "./IntentChip";

const CONNECTOR_COLORS: Record<string, string> = {
  greenhouse: "bg-emerald-100 text-emerald-700",
  lever: "bg-blue-100 text-blue-700",
  ashby: "bg-purple-100 text-purple-700",
  smartrecruiters: "bg-orange-100 text-orange-700",
  workday: "bg-rose-100 text-rose-700",
  linkedin: "bg-sky-100 text-sky-700",
  remoteok: "bg-teal-100 text-teal-700",
  themuse: "bg-pink-100 text-pink-700",
  adzuna: "bg-yellow-100 text-yellow-700",
  jobright: "bg-indigo-100 text-indigo-700",
};

const CTA_STYLE: Record<IntentKind, string> = {
  prepare_draft: "bg-amber-600 hover:bg-amber-700",
  review_draft: "bg-indigo-600 hover:bg-indigo-700",
  refresh_draft: "bg-red-600 hover:bg-red-700",
  start_apply: "bg-green-600 hover:bg-green-700",
  manual_only: "bg-gray-400 cursor-not-allowed",
};

const INTENT_RANK: Record<IntentKind, number> = {
  review_draft: 0,
  refresh_draft: 1,
  prepare_draft: 2,
  start_apply: 3,
  manual_only: 4,
};

interface Props {
  savedJobs: SavedJobWithDetails[];
  onRemove: (recordId: string) => void;
  onMarkApplied: (recordId: string) => void;
}

export default function ApplyList({ savedJobs, onRemove, onMarkApplied }: Props) {
  const [intents, setIntents] = useState<Record<string, IntentAssessment>>({});
  const [openSavedJob, setOpenSavedJob] = useState<SavedJobWithDetails | null>(null);

  // Group saved jobs by profile so we can batch per profile.
  const byProfile = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const sj of savedJobs) {
      const arr = m.get(sj.profile_id) ?? [];
      arr.push(sj.id);
      m.set(sj.profile_id, arr);
    }
    return m;
  }, [savedJobs]);

  async function refreshIntents() {
    if (byProfile.size === 0) {
      setIntents({});
      return;
    }
    const next: Record<string, IntentAssessment> = {};
    await Promise.all(
      Array.from(byProfile.entries()).map(async ([profileId, ids]) => {
        try {
          const results = await api.assessIntentBatch({
            surface: "apply_tab",
            profile_id: profileId,
            saved_job_ids: ids,
          });
          for (const r of results) {
            if (r.saved_job_id) next[r.saved_job_id] = r;
          }
        } catch {
          /* leave that profile's rows without intent — UI falls back gracefully */
        }
      })
    );
    setIntents(next);
  }

  useEffect(() => {
    void refreshIntents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedJobs]);

  const sorted = useMemo(() => {
    const ranked = savedJobs.filter(Boolean).map((sj) => {
      const intent = intents[sj.id]?.intent ?? "prepare_draft";
      return { sj, rank: INTENT_RANK[intent] ?? 99 };
    });
    ranked.sort((a, b) => a.rank - b.rank);
    return ranked.map((r) => r.sj);
  }, [savedJobs, intents]);

  if (savedJobs.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        No jobs saved yet. Tick a checkbox in the Jobs tab to save a job here.
      </div>
    );
  }

  return (
    <>
      <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-32">Company</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-40">Title</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-28 hidden md:table-cell">Location</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-24">Source</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-28">Intent</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-36">Profile</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-64">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((job) => {
              const intent = intents[job.id]?.intent;
              const action = intents[job.id]?.recommended_action;
              const ctaIntent: IntentKind = intent ?? "prepare_draft";
              const ctaLabel = action?.label ?? "Generate draft";
              const ctaDisabled = ctaIntent === "manual_only";
              return (
                <tr key={job.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900 max-w-[8rem] truncate" title={job.company ?? ""}>{job.company}</td>
                  <td className="px-4 py-3 text-gray-700 max-w-[10rem] truncate" title={job.title ?? ""}>{job.title}</td>
                  <td className="px-4 py-3 text-gray-500 hidden md:table-cell max-w-[7rem] truncate" title={job.location ?? ""}>
                    {job.location ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        CONNECTOR_COLORS[job.connector_name ?? ""] ??
                        "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {job.connector_name ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {intent ? <IntentChip intent={intent} /> : (
                      <span className="text-xs text-gray-400">…</span>
                    )}
                  </td>
                  <td className="px-4 py-3 max-w-[9rem]">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 border border-violet-200 block truncate" title={job.profile_headline ?? "Unknown profile"}>
                      {job.profile_headline ?? "Unknown profile"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 flex-nowrap">
                      <button
                        onClick={() => !ctaDisabled && setOpenSavedJob(job)}
                        disabled={ctaDisabled}
                        className={`text-xs text-white px-2.5 py-1 rounded whitespace-nowrap ${CTA_STYLE[ctaIntent]} disabled:opacity-60`}
                      >
                        {ctaLabel}
                      </button>
                      {job.url && (
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs bg-blue-600 text-white px-2.5 py-1 rounded hover:bg-blue-700 whitespace-nowrap"
                        >
                          Apply →
                        </a>
                      )}
                      <button
                        onClick={() => onMarkApplied(job.id)}
                        className="text-xs bg-green-600 text-white px-2.5 py-1 rounded hover:bg-green-700 whitespace-nowrap"
                      >
                        ✓ Applied
                      </button>
                      <button
                        onClick={() => onRemove(job.id)}
                        className="text-xs text-gray-400 hover:text-red-500 px-1"
                        title="Remove from list"
                      >
                        ×
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {openSavedJob && (
        <ApplicationDraftPanel
          savedJob={openSavedJob}
          onClose={() => setOpenSavedJob(null)}
          onChanged={() => {
            void refreshIntents();
          }}
        />
      )}
    </>
  );
}
