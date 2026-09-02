"use client";

import type { SavedJobWithDetails } from "@/types";

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

interface Props {
  savedJobs: SavedJobWithDetails[];
  onUndo: (recordId: string) => void;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function AppliedList({ savedJobs, onUndo }: Props) {
  if (savedJobs.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        No applications recorded yet. Click &ldquo;✓ Applied&rdquo; in the Apply tab to track an application.
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
      <table className="w-full min-w-[700px] text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Company</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Title</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600 hidden md:table-cell">Location</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600 w-24">Source</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Profile</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600 w-32">Applied On</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600 w-16"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {savedJobs.map((job) => (
            <tr key={job.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium text-gray-900">{job.company}</td>
              <td className="px-4 py-3 text-gray-700">{job.title}</td>
              <td className="px-4 py-3 text-gray-500 hidden md:table-cell">{job.location ?? "—"}</td>
              <td className="px-4 py-3">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${CONNECTOR_COLORS[job.connector_name ?? ""] ?? "bg-gray-100 text-gray-600"}`}>
                  {job.connector_name ?? "—"}
                </span>
              </td>
              <td className="px-4 py-3">
                <span className="text-xs px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 border border-violet-200 whitespace-nowrap">
                  {job.profile_headline ?? "Unknown profile"}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500 text-xs">
                {formatDate(job.applied_at)}
              </td>
              <td className="px-4 py-3">
                <button
                  onClick={() => onUndo(job.id)}
                  className="text-xs text-gray-400 hover:text-blue-600 underline"
                  title="Move back to Apply tab"
                >
                  Undo
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
