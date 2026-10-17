"use client";

import { useState } from "react";

import type { ScreenResult } from "@/lib/api";
import { CandidateCard } from "./CandidateCard";
import { Chip } from "./Chip";
import { ResumeDrawer, type ResumeSource } from "./ResumeDrawer";

const WORK_ARRANGEMENT_LABELS = { onsite: "On-site", hybrid: "Hybrid", remote: "Remote" } as const;

export function ResultView({
  result,
  sources,
}: {
  result: ScreenResult;
  sources: Record<string, ResumeSource>;
}) {
  const { job, ranking, errors, usage } = result;
  const [viewing, setViewing] = useState<string | null>(null);
  const viewed = ranking.find((m) => m.candidate_id === viewing);

  return (
    <section className="space-y-6" aria-live="polite">
      {job.flagged_requirements.length > 0 && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-900 dark:bg-rose-950/50">
          <h2 className="font-semibold text-rose-900 dark:text-rose-200">
            Bias check: {job.flagged_requirements.length} requirement
            {job.flagged_requirements.length > 1 ? "s" : ""} flagged and excluded from scoring
          </h2>
          <ul className="mt-2 space-y-1 text-sm text-rose-900/90 dark:text-rose-100/90">
            {job.flagged_requirements.map((f) => (
              <li key={f}>“{f}”</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-rose-800/80 dark:text-rose-200/70">
            Age, gender, civil status, height, appearance and photo requirements are never used to rank
            candidates.
          </p>
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{job.title}</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {[
            job.seniority && `Level: ${job.seniority}`,
            job.min_years_experience && `${job.min_years_experience}+ years`,
            job.location,
            job.work_arrangement && WORK_ARRANGEMENT_LABELS[job.work_arrangement],
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs font-medium uppercase tracking-wide text-slate-500">Required</span>
          {job.must_have_skills.map((s) => (
            <Chip key={s} tone="neutral">{s}</Chip>
          ))}
        </div>
        {job.nice_to_have_skills.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs font-medium uppercase tracking-wide text-slate-500">Bonus</span>
            {job.nice_to_have_skills.map((s) => (
              <Chip key={s} tone="bonus">{s}</Chip>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-slate-100">
          Ranked shortlist ({ranking.length})
        </h2>
        <ol className="space-y-3">
          {ranking.map((m, i) => (
            <CandidateCard key={m.candidate_id} match={m} rank={i + 1}
              onView={() => setViewing(m.candidate_id)} />
          ))}
        </ol>
      </div>

      {errors.length > 0 && (
        <div className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">
          Couldn&apos;t read: {errors.map((e) => `${e.candidate_id} (${e.error})`).join(", ")}
        </div>
      )}

      {viewed && (
        <ResumeDrawer match={viewed} job={job} source={sources[viewed.candidate_id]}
          onClose={() => setViewing(null)} />
      )}

      <p className="text-xs text-slate-500 dark:text-slate-400">
        {usage.llm_calls} LLM calls · {(usage.latency_ms / 1000).toFixed(1)} s ·{" "}
        {(usage.input_tokens + usage.output_tokens).toLocaleString()} tokens
      </p>
    </section>
  );
}
