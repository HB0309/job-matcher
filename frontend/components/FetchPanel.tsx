"use client";

import { useState } from "react";
import type { FetchJobsResponse } from "@/types";

const CONNECTOR_GROUPS = [
  {
    label: "Aggregators",
    connectors: ["adzuna", "jobright", "hiringcafe", "remoteok", "themuse", "indeed", "remotive", "dice"],
  },
  {
    label: "Social",
    connectors: ["linkedin"],
  },
];

const ALL_CONNECTORS = CONNECTOR_GROUPS.flatMap((g) => g.connectors);

const CONNECTOR_LABELS: Record<string, string> = {
  remoteok: "RemoteOK",
  themuse: "The Muse",
  adzuna: "Adzuna",
  jobright: "JobRight",
  hiringcafe: "Hiring Café",
  indeed: "Indeed",
  remotive: "Remotive",
  dice: "Dice",
  linkedin: "LinkedIn",
};

const CONNECTOR_COLORS: Record<string, string> = {
  remoteok: "bg-teal-100 text-teal-700 border-teal-200",
  themuse: "bg-pink-100 text-pink-700 border-pink-200",
  adzuna: "bg-yellow-100 text-yellow-700 border-yellow-200",
  jobright: "bg-indigo-100 text-indigo-700 border-indigo-200",
  hiringcafe: "bg-lime-100 text-lime-700 border-lime-200",
  indeed: "bg-blue-100 text-blue-700 border-blue-200",
  remotive: "bg-purple-100 text-purple-700 border-purple-200",
  dice: "bg-red-100 text-red-700 border-red-200",
  linkedin: "bg-sky-100 text-sky-700 border-sky-200",
};

const CONNECTOR_NOTES: Record<string, string> = {
  hiringcafe: "403 blocked",
  indeed: "feed gone",
  dice: "slower (browser)",
  linkedin: "slow (4–6 min)",
};

// Only connectors confirmed working
const DEFAULT_SELECTED = ["themuse", "remoteok", "jobright", "adzuna", "remotive", "linkedin"];

interface Props {
  onFetch: (connectors: string[], maxResults: number) => Promise<void>;
  loading: boolean;
  lastRun: FetchJobsResponse | null;
}

export default function FetchPanel({ onFetch, loading, lastRun }: Props) {
  const [selected, setSelected] = useState<string[]>(DEFAULT_SELECTED);
  const [maxResults, setMaxResults] = useState(200);

  function toggle(c: string) {
    setSelected((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );
  }

  function selectGroup(connectors: string[]) {
    const allIn = connectors.every((c) => selected.includes(c));
    if (allIn) {
      setSelected((prev) => prev.filter((c) => !connectors.includes(c)));
    } else {
      setSelected((prev) => [...new Set([...prev, ...connectors])]);
    }
  }

  const statusColors: Record<string, string> = {
    success: "bg-green-100 text-green-700",
    partial_success: "bg-amber-100 text-amber-700",
    failed: "bg-red-100 text-red-700",
    no_targets: "bg-gray-100 text-gray-600",
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 w-full space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Sources</h3>
        <div className="flex gap-2 text-xs">
          <button
            onClick={() => setSelected(ALL_CONNECTORS)}
            className="text-blue-600 hover:underline"
          >
            All
          </button>
          <span className="text-gray-300">·</span>
          <button
            onClick={() => setSelected(DEFAULT_SELECTED)}
            className="text-blue-600 hover:underline"
          >
            Default
          </button>
          <span className="text-gray-300">·</span>
          <button
            onClick={() => setSelected([])}
            className="text-gray-500 hover:underline"
          >
            None
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {CONNECTOR_GROUPS.map((group) => {
          const allIn = group.connectors.every((c) => selected.includes(c));
          const someIn = group.connectors.some((c) => selected.includes(c));
          return (
            <div key={group.label}>
              <div className="flex items-center gap-2 mb-1.5">
                <button
                  onClick={() => selectGroup(group.connectors)}
                  className="text-xs text-gray-400 hover:text-gray-600 font-medium"
                >
                  {group.label}
                </button>
                <span className="text-xs text-gray-300">
                  ({group.connectors.filter((c) => selected.includes(c)).length}/{group.connectors.length})
                </span>
              </div>
              <div className="flex gap-2 flex-wrap">
                {group.connectors.map((c) => {
                  const active = selected.includes(c);
                  const color = CONNECTOR_COLORS[c] ?? "bg-gray-100 text-gray-600 border-gray-200";
                  return (
                    <button
                      key={c}
                      onClick={() => toggle(c)}
                      className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                        active
                          ? `${color} opacity-100`
                          : "bg-gray-50 text-gray-400 border-gray-200 opacity-60"
                      }`}
                    >
                      {active ? "✓ " : ""}{CONNECTOR_LABELS[c] ?? c}
                      {CONNECTOR_NOTES[c] && (
                        <span className="ml-1 opacity-70">({CONNECTOR_NOTES[c]})</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-3 flex-wrap pt-1 border-t border-gray-100">
        <label className="text-sm text-gray-600 whitespace-nowrap">
          Max results per connector:
        </label>
        <input
          type="number"
          value={maxResults}
          onChange={(e) => setMaxResults(Number(e.target.value))}
          min={5}
          max={200}
          className="border border-gray-300 rounded px-2 py-1 text-sm w-20 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={() => onFetch(selected, maxResults)}
          disabled={loading || selected.length === 0}
          className="bg-green-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-green-700 disabled:opacity-50 flex items-center gap-2"
        >
          {loading && (
            <span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
          )}
          {loading ? "Fetching…" : `Fetch Jobs (${selected.length} sources)`}
        </button>
      </div>

      {loading && selected.includes("linkedin") && (
        <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          LinkedIn is running — this may take 4–6 minutes depending on Max results.
        </p>
      )}

      {lastRun && (
        <div className="text-sm text-gray-600 border-t border-gray-100 pt-3 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-800">Last run:</span>
            <span>{lastRun.total_jobs_fetched} fetched</span>
            <span className="text-gray-300">·</span>
            <span>{lastRun.total_jobs_matched} matched</span>
            <span className="text-gray-300">·</span>
            <span>{lastRun.target_count} targets</span>
            {lastRun.failed_targets.length > 0 && (
              <>
                <span className="text-gray-300">·</span>
                <span className="text-amber-600">
                  {lastRun.failed_targets.length} failed
                </span>
              </>
            )}
            <span
              className={`px-2 py-0.5 rounded text-xs font-medium ${
                statusColors[lastRun.status] ?? "bg-gray-100 text-gray-600"
              }`}
            >
              {lastRun.status}
            </span>
          </div>
          {lastRun.failed_targets.length > 0 && (
            <ul className="text-xs text-red-500 space-y-0.5 pl-2">
              {lastRun.failed_targets.map((f) => (
                <li key={f.target_id}>
                  {f.company_name}: {f.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
