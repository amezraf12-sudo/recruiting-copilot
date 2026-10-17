"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { CandidateMatch, JobRequirements } from "@/lib/api";
import { type Highlight, MARK, highlight } from "@/lib/highlight";
import { Chip } from "./Chip";

/** Where a candidate's original resume lives. Never sent anywhere beyond the screen request. */
export type ResumeSource = { kind: "text"; text: string; name?: string } | { kind: "pdf"; file: File };

type Tab = "parsed" | "original";

function dateRange(start: string | null, end: string | null, current: boolean) {
  return `${start ?? "?"} – ${current ? "present" : end ?? "?"}`;
}

export function ResumeDrawer({
  match,
  job,
  source,
  onClose,
}: {
  match: CandidateMatch;
  job: JobRequirements;
  source: ResumeSource | undefined;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("parsed");
  const closeRef = useRef<HTMLButtonElement>(null);

  // A blob URL for PDFs, revoked when the drawer closes or the candidate changes.
  const pdfUrl = useMemo(
    () => (source?.kind === "pdf" ? URL.createObjectURL(source.file) : null),
    [source],
  );
  useEffect(() => () => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  }, [pdfUrl]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const required = new Set(match.matched_must_haves.map((s) => s.toLowerCase()));
  const bonus = new Set(match.matched_nice_to_haves.map((s) => s.toLowerCase()));
  const terms: Highlight[] = [
    ...match.matched_must_haves.map((s) => ({ text: s, className: MARK.required, title: "Required skill" })),
    ...match.matched_nice_to_haves.map((s) => ({ text: s, className: MARK.bonus, title: "Bonus skill" })),
    ...match.suggested_matches.map((s) => ({
      text: s.evidence, className: MARK.review, title: `Possible match for "${s.skill}" (not scored)`,
    })),
  ];
  const skillTone = (s: string) =>
    required.has(s.toLowerCase()) ? "match" : bonus.has(s.toLowerCase()) ? "bonus" : "neutral";
  const { summary } = match;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true"
      aria-labelledby="resume-drawer-title">
      <button type="button" aria-label="Close" onClick={onClose}
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px]" />

      <div className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-xl dark:bg-slate-900">
        <header className="border-b border-slate-200 p-5 dark:border-slate-800">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id="resume-drawer-title" className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                {match.full_name || match.candidate_id}
              </h2>
              <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
                {match.score}/100 · {match.total_years_experience.toFixed(1)} yrs · {match.seniority} ·{" "}
                {match.meets_all_must_haves ? "all required skills" : `missing ${match.missing_must_haves.join(", ")}`}
              </p>
            </div>
            <button ref={closeRef} type="button" onClick={onClose}
              className="rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
              ✕<span className="sr-only">Close</span>
            </button>
          </div>
          <div className="mt-4 flex gap-1" role="tablist">
            {(["parsed", "original"] as const).map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  tab === t
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200"
                    : "text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}>
                {t === "parsed" ? "Parsed profile" : "Original resume"}
              </button>
            ))}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {tab === "parsed" ? (
            <div className="space-y-6 text-sm">
              <p className="text-slate-700 dark:text-slate-300">{summary.headline}</p>

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Skills</h3>
                <div className="flex flex-wrap gap-1.5">
                  {[...summary.technical_skills, ...summary.soft_skills].map((s) => (
                    <Chip key={s} tone={skillTone(s)}>{s}</Chip>
                  ))}
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Experience</h3>
                <ol className="space-y-4 border-l-2 border-slate-200 pl-4 dark:border-slate-700">
                  {summary.experience.map((e, i) => (
                    <li key={i} className="relative">
                      <span className="absolute -left-[22px] top-1.5 h-2.5 w-2.5 rounded-full bg-indigo-500" />
                      <p className="font-medium text-slate-900 dark:text-slate-100">{e.title} · {e.company}</p>
                      <p className="text-xs text-slate-500">{dateRange(e.start_date, e.end_date, e.is_current)}</p>
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-slate-700 dark:text-slate-300">
                        {e.highlights.map((h, j) => <li key={j}>{highlight(h, terms)}</li>)}
                      </ul>
                    </li>
                  ))}
                </ol>
              </section>

              {summary.certifications.length > 0 && (
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Certifications</h3>
                  <ul className="list-disc pl-5 text-slate-700 dark:text-slate-300">
                    {summary.certifications.map((c) => <li key={c}>{c}</li>)}
                  </ul>
                </section>
              )}

              <p className="text-xs text-slate-500 dark:text-slate-400">
                This is how the AI read the resume. Compare it with the original tab before deciding.
                Contact details, age, civil status and similar fields are never extracted.
              </p>
            </div>
          ) : !source ? (
            <p className="text-sm text-slate-500">The original resume isn&apos;t available for this candidate.</p>
          ) : source.kind === "pdf" ? (
            pdfUrl && (
              <iframe src={pdfUrl} title={`${match.full_name ?? match.candidate_id} resume`}
                className="h-full min-h-[70vh] w-full rounded-lg border border-slate-200 dark:border-slate-700" />
            )
          ) : (
            <div>
              <div className="mb-3 flex flex-wrap gap-3 text-xs text-slate-600 dark:text-slate-300">
                <span><mark className={`rounded px-1 ${MARK.required}`}>required</mark> skill</span>
                <span><mark className={`rounded px-1 ${MARK.bonus}`}>bonus</mark> skill</span>
                <span><mark className={`rounded px-1 ${MARK.review}`}>evidence</mark> for a review suggestion</span>
              </div>
              <pre className="whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-4 font-mono text-xs leading-relaxed text-slate-800 dark:bg-slate-950 dark:text-slate-200">
                {highlight(source.text, terms)}
              </pre>
            </div>
          )}
        </div>

        {job.flagged_requirements.length > 0 && (
          <footer className="border-t border-slate-200 p-3 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
            This job has {job.flagged_requirements.length} flagged requirements that were not used to score anyone.
          </footer>
        )}
      </div>
    </div>
  );
}
