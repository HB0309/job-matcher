"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ProfileResponse } from "@/types";

const ALL_LEVELS = [
  "new_grad",
  "entry",
  "junior",
  "mid",
  "senior",
  "staff",
  "principal",
];

interface Props {
  onCreated: (profile: ProfileResponse) => void;
}

export default function ProfileUpload({ onCreated }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [titles, setTitles] = useState("Security Engineer, Security Analyst");
  const [levels, setLevels] = useState<string[]>(["entry", "junior"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleLevel(l: string) {
    setLevels((prev) =>
      prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Please select a resume file.");
      return;
    }
    if (levels.length === 0) {
      setError("Select at least one level.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("resume", file);
      fd.append("preferred_titles", titles);
      fd.append("preferred_level", levels.join(","));
      const profile = await api.createProfile(fd);
      onCreated(profile);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-white border border-gray-200 rounded-lg p-6 space-y-4 w-full"
    >
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Resume{" "}
          <span className="text-gray-400 font-normal">(PDF or DOCX)</span>
        </label>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx"
          required
          className="block w-full text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-4 file:rounded file:border file:border-gray-300 file:text-sm file:bg-white hover:file:bg-gray-50 cursor-pointer"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Target Titles{" "}
          <span className="text-gray-400 font-normal">(comma-separated)</span>
        </label>
        <input
          value={titles}
          onChange={(e) => setTitles(e.target.value)}
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Security Engineer, Software Engineer"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Preferred Levels{" "}
          <span className="text-gray-400 font-normal">(select all that apply)</span>
        </label>
        <div className="flex flex-wrap gap-2">
          {ALL_LEVELS.map((l) => {
            const active = levels.includes(l);
            return (
              <button
                key={l}
                type="button"
                onClick={() => toggleLevel(l)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  active
                    ? "bg-blue-600 border-blue-600 text-white"
                    : "bg-white border-gray-300 text-gray-600 hover:border-blue-400"
                }`}
              >
                {l}
              </button>
            );
          })}
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="bg-blue-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
      >
        {loading && (
          <span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
        )}
        {loading ? "Uploading…" : "Upload Resume"}
      </button>
    </form>
  );
}
