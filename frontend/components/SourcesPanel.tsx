"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ConnectorSummary, SourceTargetItem } from "@/types";

export default function SourcesPanel() {
  const [open, setOpen] = useState(false);
  const [sources, setSources] = useState<ConnectorSummary[]>([]);
  const [targets, setTargets] = useState<SourceTargetItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || sources.length > 0) return;
    setLoading(true);
    Promise.all([api.getSources(), api.getSourceTargets()])
      .then(([s, t]) => {
        setSources(s.sources);
        setTargets(t.targets);
      })
      .finally(() => setLoading(false));
  }, [open, sources.length]);

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex justify-between items-center px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        <span>Sources &amp; Targets</span>
        <span className="text-gray-400 text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-gray-100 px-5 py-4">
          {loading ? (
            <p className="text-sm text-gray-400 animate-pulse">Loading…</p>
          ) : (
            <div className="space-y-5">
              {sources.map((src) => {
                const srcTargets = targets.filter(
                  (t) => t.connector === src.name
                );
                return (
                  <div key={src.name}>
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      {src.display_name}{" "}
                      <span className="font-normal normal-case text-gray-400">
                        ({srcTargets.length} targets)
                      </span>
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-1.5">
                      {srcTargets.map((t) => (
                        <div
                          key={t.id}
                          className="flex items-center gap-1.5 text-xs text-gray-600"
                          title={
                            t.last_success_at
                              ? `Last fetched: ${new Date(t.last_success_at).toLocaleDateString()}`
                              : "Never fetched"
                          }
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                              t.last_success_at
                                ? "bg-green-400"
                                : "bg-gray-300"
                            }`}
                          />
                          {t.company_name}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
