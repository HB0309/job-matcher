"use client";

import type { IntentKind } from "@/types";

const INTENT_STYLES: Record<IntentKind, { label: string; className: string }> = {
  prepare_draft: {
    label: "Draft needed",
    className: "bg-amber-100 text-amber-700 border-amber-200",
  },
  review_draft: {
    label: "Review draft",
    className: "bg-indigo-100 text-indigo-700 border-indigo-200",
  },
  refresh_draft: {
    label: "Stale",
    className: "bg-red-100 text-red-700 border-red-200",
  },
  start_apply: {
    label: "Ready to apply",
    className: "bg-green-100 text-green-700 border-green-200",
  },
  manual_only: {
    label: "Applied",
    className: "bg-gray-100 text-gray-600 border-gray-200",
  },
};

export default function IntentChip({ intent }: { intent: IntentKind }) {
  const style = INTENT_STYLES[intent];
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium border whitespace-nowrap ${style.className}`}
    >
      {style.label}
    </span>
  );
}
