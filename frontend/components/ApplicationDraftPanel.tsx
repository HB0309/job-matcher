"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { ApplicationDraft, JobDetail, SavedJobWithDetails, TailoredResumeResponse } from "@/types";

interface Props {
  savedJob: SavedJobWithDetails;
  onClose: () => void;
  onChanged: () => void;
}

export default function ApplicationDraftPanel({ savedJob, onClose, onChanged }: Props) {
  const [draft, setDraft] = useState<ApplicationDraft | null>(null);
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tailored, setTailored] = useState<TailoredResumeResponse | null>(null);
  const [tailorNotes, setTailorNotes] = useState("");
  const [tailorBusy, setTailorBusy] = useState(false);
  const [tailorError, setTailorError] = useState<string | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyMsg, setApplyMsg] = useState<string | null>(null);

  async function loadOrCreate() {
    setLoading(true);
    setError(null);
    try {
      const d = await api.createDraft({
        profile_id: savedJob.profile_id,
        saved_job_id: savedJob.id,
      });
      setDraft(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadOrCreate();
    api.lookupTailoredResume(savedJob.profile_id, savedJob.id)
      .then(setTailored)
      .catch(() => setTailored(null));
    api.getJob(savedJob.job_id, savedJob.profile_id)
      .then(setJobDetail)
      .catch(() => setJobDetail(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedJob.id]);

  async function generateTailoredResume() {
    setTailorBusy(true);
    setTailorError(null);
    try {
      const result = await api.createTailoredResume({
        profile_id: savedJob.profile_id,
        saved_job_id: savedJob.id,
        user_notes: tailorNotes || null,
      });
      setTailored(result);
    } catch (e) {
      setTailorError(e instanceof Error ? e.message : String(e));
    } finally {
      setTailorBusy(false);
    }
  }

  async function autoApply() {
    if (!draft) return;
    setApplyBusy(true);
    setApplyMsg(null);
    try {
      await api.triggerAutoApply(draft.id);
      setApplyMsg("Browser opened — review the filled form and click Submit when ready.");
    } catch (e) {
      setApplyMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setApplyBusy(false);
    }
  }

  async function patch(status: "approved" | "discarded" | "review_pending") {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.patchDraft(draft.id, { status });
      setDraft(updated);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      // Mark stale first if approved, so backend regenerates.
      if (draft.status !== "stale" && draft.status !== "discarded") {
        await api.patchDraft(draft.id, { status: "stale" });
      }
      const next = await api.createDraft({
        profile_id: savedJob.profile_id,
        saved_job_id: savedJob.id,
      });
      setDraft(next);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const matched = draft?.keyword_gap_summary?.matched ?? [];
  const missing = draft?.keyword_gap_summary?.missing ?? [];
  const tailoredJson = (draft?.tailored_resume_json ?? {}) as Record<string, unknown>;
  const qa = (draft?.qa_answers_json ?? {}) as Record<string, unknown>;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-5xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between sticky top-0 bg-white z-10">
          <div>
            <div className="text-xs text-gray-500">Application draft</div>
            <h2 className="text-lg font-semibold text-gray-900">
              {savedJob.title} · {savedJob.company}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Job details */}
        {jobDetail && (
          <div className="px-6 py-4 border-b border-gray-100 bg-gray-50 space-y-2">
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
              {jobDetail.location && <span>📍 {jobDetail.location}</span>}
              {jobDetail.normalized_level && <span className="capitalize">{jobDetail.normalized_level}</span>}
              <span className="text-indigo-600 font-medium">
                Match {Math.round((jobDetail.overall_score ?? 0) * 100)}%
              </span>
              {savedJob.url && (
                <a href={savedJob.url} target="_blank" rel="noopener noreferrer"
                  className="ml-auto text-blue-600 hover:underline font-medium text-xs">
                  View posting →
                </a>
              )}
            </div>
            {jobDetail.raw_description && (
              <details className="text-xs text-gray-700">
                <summary className="cursor-pointer font-medium text-gray-800 select-none py-1">
                  Job Description
                </summary>
                <div className="mt-2 max-h-64 overflow-y-auto bg-white border border-gray-200 rounded p-3 whitespace-pre-wrap leading-relaxed">
                  {jobDetail.raw_description}
                </div>
              </details>
            )}
          </div>
        )}

        {loading && (
          <div className="p-8 text-center text-gray-500 text-sm">Generating draft…</div>
        )}

        {error && (
          <div className="m-6 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
            {error}
          </div>
        )}

        {!loading && draft && (
          <div className="p-6 space-y-6 text-sm">
            <div className="flex items-center gap-3">
              <span
                className={`text-xs px-2 py-0.5 rounded-full font-medium border ${
                  draft.status === "approved"
                    ? "bg-green-100 text-green-700 border-green-200"
                    : draft.status === "stale"
                    ? "bg-red-100 text-red-700 border-red-200"
                    : draft.status === "discarded"
                    ? "bg-gray-100 text-gray-600 border-gray-200"
                    : "bg-indigo-100 text-indigo-700 border-indigo-200"
                }`}
              >
                {draft.status}
              </span>
              <span className="text-xs text-gray-500">
                confidence {Math.round((draft.confidence_score ?? 0) * 100)}%
              </span>
              <span className="text-xs text-gray-400">
                version {draft.tailored_resume_version}
              </span>
            </div>

            <section>
              <h3 className="font-semibold text-gray-800 mb-1">Fit summary</h3>
              <p className="text-gray-700 leading-relaxed">
                {draft.fit_summary ?? "—"}
              </p>
            </section>

            <section>
              <h3 className="font-semibold text-gray-800 mb-2">Keyword gaps</h3>
              <div className="flex flex-wrap gap-1.5 mb-2">
                <span className="text-xs text-gray-500 mr-1">Matched:</span>
                {matched.length === 0 && (
                  <span className="text-xs text-gray-400">none</span>
                )}
                {matched.map((s) => (
                  <span
                    key={`m-${s}`}
                    className="text-xs px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200"
                  >
                    {s}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5">
                <span className="text-xs text-gray-500 mr-1">Missing:</span>
                {missing.length === 0 && (
                  <span className="text-xs text-gray-400">none</span>
                )}
                {missing.map((s) => (
                  <span
                    key={`x-${s}`}
                    className="text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </section>

            <section>
              <h3 className="font-semibold text-gray-800 mb-1">Tailored resume preview</h3>
              <pre className="bg-gray-50 border border-gray-200 rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap text-black">
                {JSON.stringify(tailoredJson, null, 2)}
              </pre>
            </section>

            <section>
              <h3 className="font-semibold text-gray-800 mb-1">Application Q&amp;A</h3>
              <pre className="bg-gray-50 border border-gray-200 rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap text-black">
                {JSON.stringify(qa, null, 2)}
              </pre>
            </section>

            <section className="border-t border-gray-100 pt-4">
              <h3 className="font-semibold text-gray-800 mb-1">Tailored Resume</h3>
              <p className="text-xs text-gray-500 mb-2">
                Uses Gemini + Groq to rewrite your resume for this specific job, then compiles to PDF.
              </p>

              {tailored ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">
                      version {tailored.version}
                    </span>
                    {tailored.has_pdf && (
                      <a
                        href={api.downloadPdfUrl(tailored.id)}
                        download={`resume_tailored_v${tailored.version}.pdf`}
                        className="text-xs bg-indigo-600 text-white px-2.5 py-1 rounded hover:bg-indigo-700"
                      >
                        Download PDF
                      </a>
                    )}
                  </div>
                  {tailored.tailoring_rationale && (
                    <p className="text-xs text-gray-600 italic">{tailored.tailoring_rationale}</p>
                  )}
                  <div className="space-y-2">
                    <textarea
                      value={tailorNotes}
                      onChange={(e) => setTailorNotes(e.target.value)}
                      placeholder="Instructions for this version? e.g. 'emphasize detection engineering, add the CTF project'"
                      rows={2}
                      className="w-full text-xs border border-gray-300 rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-400 text-black"
                    />
                    <button
                      onClick={generateTailoredResume}
                      disabled={tailorBusy}
                      className="text-xs bg-white border border-gray-300 text-gray-700 px-2.5 py-1 rounded hover:bg-gray-50 disabled:opacity-50"
                    >
                      {tailorBusy ? "Regenerating…" : "Regenerate"}
                    </button>
                  </div>
                  {tailored.has_pdf && (
                    <div className="border border-gray-200 rounded overflow-hidden">
                      <iframe
                        src={api.downloadPdfUrl(tailored.id)}
                        className="w-full"
                        style={{ height: "75vh" }}
                        title="Tailored Resume PDF"
                      />
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <textarea
                    value={tailorNotes}
                    onChange={(e) => setTailorNotes(e.target.value)}
                    placeholder="Any special emphasis? e.g. 'focus on detection engineering, downplay ML projects'"
                    rows={2}
                    className="w-full text-xs border border-gray-300 rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-400 text-black"
                  />
                  <button
                    onClick={generateTailoredResume}
                    disabled={tailorBusy}
                    className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {tailorBusy ? "Generating resume… (~30s)" : "Generate Tailored Resume"}
                  </button>
                </div>
              )}

              {tailorError && (
                <p className="mt-2 text-xs text-red-600">{tailorError}</p>
              )}
            </section>
          </div>
        )}

        {!loading && draft && (
          <>
            {applyMsg && (
              <div className={`mx-6 mb-2 px-3 py-2 rounded text-xs ${applyMsg.startsWith("Browser") ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
                {applyMsg}
              </div>
            )}

            <div className="px-6 py-4 border-t border-gray-200 flex flex-wrap gap-2 justify-end sticky bottom-0 bg-white">
              {draft.status === "approved" && (
                <button
                  onClick={autoApply}
                  disabled={applyBusy}
                  className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  {applyBusy ? "Opening browser…" : "Auto Apply"}
                </button>
              )}
              <button
                onClick={regenerate}
                disabled={busy}
                className="text-xs bg-white border border-gray-300 text-gray-700 px-3 py-1.5 rounded hover:bg-gray-50 disabled:opacity-50"
              >
                Regenerate
              </button>
              <button
                onClick={() => patch("discarded")}
                disabled={busy || draft.status === "discarded"}
                className="text-xs bg-white border border-red-300 text-red-700 px-3 py-1.5 rounded hover:bg-red-50 disabled:opacity-50"
              >
                Discard
              </button>
              {draft.status !== "approved" ? (
                <button
                  onClick={() => patch("approved")}
                  disabled={busy}
                  className="text-xs bg-green-600 text-white px-3 py-1.5 rounded hover:bg-green-700 disabled:opacity-50"
                >
                  Approve
                </button>
              ) : (
                <button
                  onClick={() => patch("review_pending")}
                  disabled={busy}
                  className="text-xs bg-yellow-600 text-white px-3 py-1.5 rounded hover:bg-yellow-700 disabled:opacity-50"
                >
                  Unapprove
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
