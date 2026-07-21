"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ScheduledFetch } from "@/types";

const INTERVAL_OPTIONS = [
  { label: "Every 6 hours", value: 6 },
  { label: "Every 12 hours", value: 12 },
  { label: "Every 24 hours (daily)", value: 24 },
  { label: "Every 48 hours", value: 48 },
];

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

interface Props {
  profileId: string;
}

export default function SchedulePanel({ profileId }: Props) {
  const [schedule, setSchedule] = useState<ScheduledFetch | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [intervalHours, setIntervalHours] = useState(24);

  useEffect(() => {
    setLoading(true);
    api.getSchedules(profileId)
      .then((list) => {
        const s = list[0] ?? null;
        setSchedule(s);
        if (s) setIntervalHours(s.interval_hours);
      })
      .catch(() => setSchedule(null))
      .finally(() => setLoading(false));
  }, [profileId]);

  async function toggleEnabled() {
    setSaving(true);
    try {
      if (!schedule) {
        const s = await api.createSchedule({ profile_id: profileId, interval_hours: intervalHours });
        setSchedule(s);
      } else if (schedule.enabled) {
        const s = await api.updateSchedule(schedule.id, { enabled: false });
        setSchedule(s);
      } else {
        const s = await api.updateSchedule(schedule.id, { enabled: true });
        setSchedule(s);
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleIntervalChange(hours: number) {
    setIntervalHours(hours);
    if (!schedule) return;
    setSaving(true);
    try {
      const s = await api.updateSchedule(schedule.id, { interval_hours: hours });
      setSchedule(s);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return null;

  const enabled = schedule?.enabled ?? false;

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 bg-gray-50 border border-gray-200 rounded-lg text-sm">
      <span className="font-medium text-gray-700">Auto-fetch</span>

      <select
        value={intervalHours}
        onChange={(e) => handleIntervalChange(Number(e.target.value))}
        disabled={saving}
        className="text-xs border border-gray-300 rounded px-2 py-1 bg-white text-gray-700 disabled:opacity-50"
      >
        {INTERVAL_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      <button
        onClick={toggleEnabled}
        disabled={saving}
        className={`text-xs px-3 py-1 rounded-full font-medium border transition-colors disabled:opacity-50 ${
          enabled
            ? "bg-green-100 text-green-700 border-green-300 hover:bg-green-200"
            : "bg-gray-100 text-gray-500 border-gray-300 hover:bg-gray-200"
        }`}
      >
        {enabled ? "● Enabled" : "○ Disabled"}
      </button>

      {schedule && (
        <span className="text-xs text-gray-400">
          {schedule.last_run_at ? `Last: ${formatDate(schedule.last_run_at)}` : "Not run yet"}
          {" · "}
          {enabled && schedule.next_run_at ? `Next: ${formatDate(schedule.next_run_at)}` : ""}
        </span>
      )}
    </div>
  );
}
