"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CombinedJobItem, JobDetail, ScoreExplanation } from "@/types";

interface Props {
  jobs: CombinedJobItem[];
  savedSet: Set<string>;
  appliedSet: Set<string>;
  onToggleSave: (jobId: string, profileId: string) => void;
  latestRunIds?: string[];
}

const CONNECTOR_COLORS: Record<string, string> = {
  linkedin: "bg-sky-100 text-sky-700",
  remoteok: "bg-teal-100 text-teal-700",
  themuse: "bg-pink-100 text-pink-700",
  adzuna: "bg-yellow-100 text-yellow-700",
  jobright: "bg-indigo-100 text-indigo-700",
  hiringcafe: "bg-lime-100 text-lime-700",
  indeed: "bg-blue-100 text-blue-700",
  dice: "bg-red-100 text-red-700",
  remotive: "bg-purple-100 text-purple-700",
};

function ScoreBar({ value, label, note, chips }: {
  value: number;
  label: string;
  note?: string;
  chips?: { matched: string[]; missing: string[] };
}) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-amber-400" : "bg-red-400";
  const MAX_CHIPS = 6;
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3 text-xs">
        <span className="w-16 text-gray-500 text-right shrink-0">{label}</span>
        <div className="flex-1 bg-gray-100 rounded-full h-2">
          <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span className="w-8 text-gray-700 font-medium shrink-0">{pct}%</span>
      </div>
      {note && (
        <p className="text-[11px] text-gray-400 pl-[76px]">{note}</p>
      )}
      {chips && (chips.matched.length > 0 || chips.missing.length > 0) && (
        <div className="pl-[76px] flex flex-wrap gap-1 pt-0.5">
          {chips.matched.slice(0, MAX_CHIPS).map((s) => (
            <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-700 font-medium">{s}</span>
          ))}
          {chips.matched.length > MAX_CHIPS && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-600">+{chips.matched.length - MAX_CHIPS} more</span>
          )}
          {chips.missing.slice(0, MAX_CHIPS).map((s) => (
            <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 font-medium">{s}</span>
          ))}
          {chips.missing.length > MAX_CHIPS && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-400">+{chips.missing.length - MAX_CHIPS} missing</span>
          )}
        </div>
      )}
    </div>
  );
}

function buildSkillsNote(ex: ScoreExplanation): string {
  if (ex.skill_count_job === 0) return "no skill tags on this job";
  return `${ex.matched_skills.length} / ${ex.skill_count_job} skills matched`;
}

function JobDialog({
  jobId,
  profileId,
  isSaved,
  isApplied,
  onToggleSave,
  onClose,
}: {
  jobId: string;
  profileId: string;
  isSaved: boolean;
  isApplied: boolean;
  onToggleSave: (id: string, profileId: string) => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getJob(jobId, profileId)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [jobId, profileId]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-gray-100">
          <div className="flex-1 min-w-0 pr-4">
            {loading ? (
              <div className="h-5 bg-gray-100 rounded animate-pulse w-48 mb-2" />
            ) : detail ? (
              <>
                <h2 className="text-base font-semibold text-gray-900 leading-snug">{detail.title}</h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  {detail.company}
                  {detail.location ? ` · ${detail.location}` : ""}
                  {detail.normalized_level ? ` · ${detail.normalized_level.replace("_", " ")}` : ""}
                </p>
              </>
            ) : null}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none shrink-0 mt-0.5"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-5">
          {loading && (
            <div className="space-y-3 animate-pulse">
              <div className="h-3 bg-gray-100 rounded w-3/4" />
              <div className="h-3 bg-gray-100 rounded w-1/2" />
              <div className="h-3 bg-gray-100 rounded w-2/3" />
            </div>
          )}

          {error && <p className="text-sm text-red-500">{error}</p>}

          {detail && (
            <>
              {/* Score breakdown */}
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Match score</p>
                <div className="space-y-3">
                  <ScoreBar
                    value={detail.scores.overall}
                    label="Overall"
                    note="skills 35% · level 50% · location 15%"
                  />
                  <ScoreBar
                    value={detail.scores.skills}
                    label="Skills"
                    note={detail.score_explanation ? buildSkillsNote(detail.score_explanation) : undefined}
                    chips={detail.score_explanation ? {
                      matched: detail.score_explanation.matched_skills,
                      missing: detail.score_explanation.missing_skills,
                    } : undefined}
                  />
                  <ScoreBar
                    value={detail.scores.level}
                    label="Level"
                    note={detail.score_explanation?.level_explanation}
                  />
                  <ScoreBar
                    value={detail.scores.location}
                    label="Location"
                    note={detail.score_explanation?.location_explanation}
                  />
                </div>
              </div>

              {/* Keywords / tags */}
              {detail.tags && detail.tags.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                    Keywords & technologies
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.tags.map((tag) => (
                      <span
                        key={tag}
                        className="bg-blue-50 text-blue-700 border border-blue-100 text-xs px-2.5 py-1 rounded-full font-medium"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Full description */}
              {detail.raw_description && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                      Job description
                    </p>
                    {detail.connector === "adzuna" && (
                      <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                        preview only — click Apply for full description
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap bg-gray-50 rounded-lg p-4 border border-gray-100 max-h-72 overflow-y-auto">
                    {detail.raw_description}
                  </div>
                </div>
              )}

              {!detail.raw_description && (
                <p className="text-sm text-gray-400 italic">No description available — click Apply to view the full listing.</p>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 gap-3">
          <div className="flex items-center gap-2">
            {!isApplied && (
              <button
                onClick={() => onToggleSave(jobId, profileId)}
                className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                  isSaved
                    ? "border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100"
                    : "border-gray-300 text-gray-600 hover:bg-gray-50"
                }`}
              >
                {isSaved ? "✓ Saved" : "Save"}
              </button>
            )}
            {isApplied && (
              <span className="text-xs text-gray-400 font-medium">✓ Applied</span>
            )}
          </div>
          {detail && (
            <a
              href={detail.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium"
            >
              Apply →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

const PAGE_SIZE = 50;
const LEVEL_ORDER = ["new_grad", "entry", "junior", "mid", "senior", "staff", "principal"];
const LEVEL_LABELS: Record<string, string> = {
  new_grad: "New Grad", entry: "Entry", junior: "Junior",
  mid: "Mid", senior: "Senior", staff: "Staff", principal: "Principal",
};

export default function JobsList({ jobs, savedSet, appliedSet, onToggleSave, latestRunIds }: Props) {
  const [dialogJobId, setDialogJobId] = useState<string | null>(null);
  const [connectorFilter, setConnectorFilter] = useState("all");
  const [maxLevel, setMaxLevel] = useState("all");
  const [minScore, setMinScore] = useState(0);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"score" | "recent">("score");
  const [newOnly, setNewOnly] = useState(false);
  const [page, setPage] = useState(0);

  const connectors = [...new Set(jobs.map((j) => j.connector))];
  const maxLevelIdx = maxLevel === "all" ? Infinity : LEVEL_ORDER.indexOf(maxLevel);

  const filtered = jobs
    .filter((j) => connectorFilter === "all" || j.connector === connectorFilter)
    .filter((j) => j.overall_score >= minScore / 100)
    .filter((j) => {
      if (maxLevel === "all") return true;
      if (!j.normalized_level) return true;
      const idx = LEVEL_ORDER.indexOf(j.normalized_level);
      return idx === -1 || idx <= maxLevelIdx;
    })
    .filter(
      (j) =>
        !search ||
        j.title.toLowerCase().includes(search.toLowerCase()) ||
        j.company.toLowerCase().includes(search.toLowerCase())
    )
    .filter(
      (j) =>
        !newOnly ||
        !latestRunIds ||
        latestRunIds.length === 0 ||
        (j.fetch_run_id != null && latestRunIds.includes(j.fetch_run_id))
    );

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === "recent") {
      // Sort by when WE fetched it (fetched_at), not when the job was posted
      const ta = a.fetched_at ? new Date(a.fetched_at).getTime() : 0;
      const tb = b.fetched_at ? new Date(b.fetched_at).getTime() : 0;
      return tb - ta;
    }
    return b.overall_score - a.overall_score;
  });

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const paginated = sorted.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const dialogProfileId = dialogJobId
    ? jobs.find((j) => j.job_id === dialogJobId)?.matches[0]?.profile_id ?? null
    : null;

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex gap-3 flex-wrap items-center">
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          placeholder="Search title / company…"
          className="border border-gray-300 rounded px-3 py-1.5 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={connectorFilter}
          onChange={(e) => { setConnectorFilter(e.target.value); setPage(0); }}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All connectors</option>
          {connectors.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          value={maxLevel}
          onChange={(e) => { setMaxLevel(e.target.value); setPage(0); }}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All levels</option>
          {LEVEL_ORDER.map((l) => <option key={l} value={l}>≤ {LEVEL_LABELS[l]}</option>)}
        </select>
        <div className="flex items-center rounded border border-gray-300 overflow-hidden text-sm">
          <button
            onClick={() => { setSortBy("score"); setPage(0); }}
            className={`px-3 py-1.5 ${sortBy === "score" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
          >
            Best match
          </button>
          <button
            onClick={() => { setSortBy("recent"); setPage(0); }}
            className={`px-3 py-1.5 border-l border-gray-300 ${sortBy === "recent" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
          >
            Most recent
          </button>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span>Min score:</span>
          <input
            type="range" min={0} max={100} step={5} value={minScore}
            onChange={(e) => { setMinScore(Number(e.target.value)); setPage(0); }}
            className="w-24"
          />
          <span className="w-8">{minScore}%</span>
        </div>
        {!!latestRunIds?.length && (
          <button
            onClick={() => { setNewOnly((v) => !v); setPage(0); }}
            className={`text-xs px-2.5 py-1.5 rounded border font-medium transition-colors ${
              newOnly
                ? "bg-green-600 text-white border-green-600"
                : "border-gray-300 text-gray-600 hover:bg-gray-50"
            }`}
          >
            {newOnly ? "✓ New only" : "New only"}
          </button>
        )}
        <span className="text-sm text-gray-400">{sorted.length} results</span>
        {totalPages > 1 && (
          <span className="text-sm text-gray-400 ml-auto">Page {safePage + 1} / {totalPages}</span>
        )}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-4 py-3 w-8"></th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-16">Score</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Company</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Title</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 hidden md:table-cell">Location</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-24">Source</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Profiles</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {paginated.map((job) => {
              const pct = Math.round(job.overall_score * 100);
              const scoreColor =
                pct >= 70 ? "text-green-700 bg-green-50" :
                pct >= 40 ? "text-amber-700 bg-amber-50" :
                "text-red-700 bg-red-50";
              const isNew =
                !!latestRunIds?.length && !!job.fetch_run_id && latestRunIds.includes(job.fetch_run_id);
              const primaryProfileId = job.matches[0].profile_id;
              const saveKey = `${primaryProfileId}:${job.job_id}`;

              return (
                <tr
                  key={job.job_id}
                  onClick={() => setDialogJobId(job.job_id)}
                  className="hover:bg-gray-50 cursor-pointer"
                >
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    {appliedSet.has(saveKey) ? (
                      <span className="text-xs text-gray-400 font-medium">✓</span>
                    ) : (
                      <input
                        type="checkbox"
                        checked={savedSet.has(saveKey)}
                        onChange={() => onToggleSave(job.job_id, primaryProfileId)}
                        className="w-4 h-4 accent-blue-600 cursor-pointer"
                      />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center justify-center w-11 h-6 rounded text-xs font-bold ${scoreColor}`}>
                      {pct}%
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">{job.company}</td>
                  <td className="px-4 py-3 text-gray-700">
                    {job.title}
                    {isNew && (
                      <span className="ml-2 text-[10px] font-bold px-1.5 py-0.5 rounded bg-green-100 text-green-700 align-middle">NEW</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500 hidden md:table-cell">{job.location ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${CONNECTOR_COLORS[job.connector] ?? "bg-gray-100 text-gray-600"}`}>
                      {job.connector}
                    </span>
                  </td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex flex-wrap gap-1">
                      {job.matches.map((m, i) => {
                        const label = m.profile_titles.length > 0
                          ? m.profile_titles.slice(0, 2).join(" / ")
                          : m.profile_headline ?? "Profile";
                        return (
                          <span
                            key={m.profile_id}
                            title={m.profile_headline ?? undefined}
                            className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap ${
                              i === 0
                                ? "bg-blue-50 text-blue-700 border border-blue-200"
                                : "bg-gray-100 text-gray-500"
                            }`}
                          >
                            {label.slice(0, 24)} · {Math.round(m.overall_score * 100)}%
                          </span>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="text-center py-10 text-gray-400 text-sm">No jobs match your filters.</div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span className="text-sm text-gray-500">
            {safePage * PAGE_SIZE + 1}–{Math.min((safePage + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={safePage >= totalPages - 1}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}

      {/* Job detail dialog */}
      {dialogJobId && dialogProfileId && (
        <JobDialog
          jobId={dialogJobId}
          profileId={dialogProfileId}
          isSaved={savedSet.has(`${dialogProfileId}:${dialogJobId}`)}
          isApplied={appliedSet.has(`${dialogProfileId}:${dialogJobId}`)}
          onToggleSave={onToggleSave}
          onClose={() => setDialogJobId(null)}
        />
      )}
    </div>
  );
}
