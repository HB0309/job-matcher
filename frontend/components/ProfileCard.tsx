"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ProfileResponse } from "@/types";

const LEVEL_OPTIONS = ["new_grad", "entry", "junior", "mid", "senior", "staff", "principal"];

interface Props {
  profile: ProfileResponse;
  onReset: () => void;
  onDelete: () => void;
  onUpdated: (updated: ProfileResponse) => void;
}

export default function ProfileCard({ profile, onReset, onDelete, onUpdated }: Props) {
  const [editing, setEditing] = useState(false);
  const [titles, setTitles] = useState(profile.preferred_titles.join(", "));
  const [levels, setLevels] = useState<string[]>(profile.preferred_level);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [staleCount, setStaleCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const saved = await api.getSavedJobs(profile.profile_id);
        const ids = saved.filter((s) => s.status !== "applied").map((s) => s.id);
        if (ids.length === 0) {
          if (!cancelled) setStaleCount(0);
          return;
        }
        const intents = await api.assessIntentBatch({
          surface: "profile_edit",
          profile_id: profile.profile_id,
          saved_job_ids: ids,
        });
        if (!cancelled) {
          setStaleCount(intents.filter((i) => i.intent === "refresh_draft").length);
        }
      } catch {
        if (!cancelled) setStaleCount(0);
      }
    }
    void check();
    return () => {
      cancelled = true;
    };
  }, [profile.profile_id, profile.updated_at]);

  function toggleLevel(l: string) {
    setLevels((prev) => prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    e.stopPropagation();
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.updateProfile(profile.profile_id, {
        preferred_titles: titles.split(",").map((t) => t.trim()).filter(Boolean),
        preferred_level: levels,
      });
      onUpdated(updated);
      setEditing(false);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  function handleCancelEdit(e: React.MouseEvent) {
    e.stopPropagation();
    setTitles(profile.preferred_titles.join(", "));
    setLevels(profile.preferred_level);
    setSaveError(null);
    setEditing(false);
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 w-full">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-medium text-gray-900">
            {profile.headline ?? "Profile loaded"}
          </p>
          <p className="text-sm text-gray-500 mt-0.5">
            {profile.years_experience != null
              ? `${profile.years_experience} yrs exp`
              : ""}
          </p>
        </div>
        <div className="flex gap-2 shrink-0 ml-4">
          <button
            onClick={(e) => { e.stopPropagation(); setEditing((v) => !v); }}
            className="text-xs text-gray-400 hover:text-gray-600 border border-gray-200 rounded px-2 py-1"
          >
            Edit
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onReset(); }}
            className="text-xs text-gray-400 hover:text-gray-600 border border-gray-200 rounded px-2 py-1"
          >
            Switch
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (confirm("Delete this profile and all its job matches?")) onDelete();
            }}
            className="text-xs text-red-400 hover:text-red-600 border border-red-200 rounded px-2 py-1"
          >
            Delete
          </button>
        </div>
      </div>

      {staleCount > 0 && !editing && (
        <div className="mt-3 px-3 py-2 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center justify-between gap-2">
          <span>
            {staleCount} application draft{staleCount === 1 ? "" : "s"} marked stale —
            regenerate from the Apply tab.
          </span>
        </div>
      )}

      {/* Inline edit form */}
      {editing && (
        <form
          onSubmit={handleSave}
          onClick={(e) => e.stopPropagation()}
          className="mt-4 space-y-3 border-t border-gray-100 pt-4"
        >
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Job titles (comma-separated)
            </label>
            <input
              value={titles}
              onChange={(e) => setTitles(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. Software Engineer, Backend Engineer"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Levels
            </label>
            <div className="flex flex-wrap gap-1.5">
              {LEVEL_OPTIONS.map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => toggleLevel(l)}
                  className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                    levels.includes(l)
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "bg-white text-gray-500 border-gray-300 hover:border-gray-400"
                  }`}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>
          {saveError && <p className="text-xs text-red-500">{saveError}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={handleCancelEdit}
              className="text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded px-3 py-1.5"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Display (shown when not editing) */}
      {!editing && (
        <>
          {profile.preferred_titles?.length > 0 && (
            <p className="text-sm text-gray-600 mt-2">
              Titles: {profile.preferred_titles.join(", ")}
            </p>
          )}

          {profile.preferred_level?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {profile.preferred_level.map((l) => (
                <span
                  key={l}
                  className="bg-indigo-50 text-indigo-700 text-xs px-2 py-0.5 rounded-full font-medium"
                >
                  {l}
                </span>
              ))}
            </div>
          )}

          {profile.skills?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {profile.skills.slice(0, 20).map((s) => (
                <span
                  key={s}
                  className="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full"
                >
                  {s}
                </span>
              ))}
              {profile.skills.length > 20 && (
                <span className="text-xs text-gray-400">
                  +{profile.skills.length - 20} more
                </span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
