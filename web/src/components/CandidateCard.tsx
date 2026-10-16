"use client";

import { useState } from "react";

import type { CandidateMatch } from "@/lib/api";
import { Chip } from "./Chip";

function scoreTone(score: number) {
  if (score >= 75) return "bg-emerald-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-slate-400";
}

export function CandidateCard({ match, rank }: { match: CandidateMatch; rank: number }) {
  const [open, setOpen] = useState(rank === 1);
  const name = match.full_name || match.candidate_id;

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start gap-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {rank}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">{name}</h3>
            {match.meets_all_must_haves ? (
              <Chip tone="match">All required skills</Chip>
            ) : (
              <Chip tone="missing">Missing {match.missing_must_haves.length} required</Chip>
            )}
            <span className="text-sm text-slate-500 dark:text-slate-400">
              {match.total_years_experience.toFixed(1)} yrs · {match.seniority}
            </span>
          </div>

          <div className="mt-3 flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div className={`h-full ${scoreTone(match.score)}`} style={{ width: `${match.score}%` }} />
            </div>
            <span className="w-14 text-right text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {match.score}/100
            </span>
          </div>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {match.matched_must_haves.map((s) => (
              <Chip key={`m-${s}`} tone="match">✓ {s}</Chip>
            ))}
            {match.missing_must_haves.map((s) => (
              <Chip key={`x-${s}`} tone="missing">✗ {s}</Chip>
            ))}
            {match.matched_nice_to_haves.map((s) => (
              <Chip key={`n-${s}`} tone="bonus">+ {s}</Chip>
            ))}
          </div>

          {match.suggested_matches.length > 0 && (
            <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-950/50">
              <p className="font-medium text-amber-900 dark:text-amber-200">
                Review: may have these under different wording (not scored)
              </p>
              <ul className="mt-1 space-y-1 text-amber-900/90 dark:text-amber-100/90">
                {match.suggested_matches.map((s) => (
                  <li key={s.skill}>
                    <span className="font-medium">{s.skill}</span>: “{s.evidence}”
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="mt-3 text-sm font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
            aria-expanded={open}
          >
            {open ? "Hide" : "Show"} why this score
          </button>
          {open && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
              {match.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </li>
  );
}
