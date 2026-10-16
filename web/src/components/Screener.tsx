"use client";

import { useEffect, useState } from "react";

import { ApiError, type ScreenResult, screenFiles, screenTexts } from "@/lib/api";
import samples from "@/lib/samples.json";
import { AssistantPanel } from "./AssistantPanel";
import { ResultView } from "./ResultView";

const MAX_FILES = 10;
const MIN_JOB_CHARS = 50;
const WAKE_UP_HINT_AFTER_S = 12;

type Source = "samples" | "upload";

export function Screener() {
  const [jobText, setJobText] = useState(samples.jobs[0].text);
  const [sampleJobId, setSampleJobId] = useState(samples.jobs[0].id);
  const [source, setSource] = useState<Source>("samples");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenResult | null>(null);
  const [screenRun, setScreenRun] = useState(0);

  useEffect(() => {
    if (!loading) return;
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [loading]);

  function pickSampleJob(id: string) {
    const job = samples.jobs.find((j) => j.id === id);
    setSampleJobId(id);
    if (job) setJobText(job.text);
  }

  function pickFiles(list: FileList | null) {
    const picked = Array.from(list ?? []);
    setError(picked.length > MAX_FILES ? `Upload at most ${MAX_FILES} resumes.` : null);
    setFiles(picked.slice(0, MAX_FILES));
  }

  const jobTooShort = jobText.trim().length < MIN_JOB_CHARS;
  const noFiles = source === "upload" && files.length === 0;

  async function run() {
    setElapsed(0);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res =
        source === "samples"
          ? await screenTexts(jobText, samples.resumes)
          : await screenFiles(jobText, files);
      setResult(res);
      setScreenRun((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="font-semibold text-slate-900 dark:text-slate-100">1. Job posting</h2>
          <label className="mt-3 block text-sm text-slate-600 dark:text-slate-300">
            Start from a sample
            <select
              value={sampleJobId}
              onChange={(e) => pickSampleJob(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              {samples.jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.label}
                </option>
              ))}
            </select>
          </label>
          <label className="mt-3 block text-sm text-slate-600 dark:text-slate-300">
            …or paste your own
            <textarea
              value={jobText}
              onChange={(e) => setJobText(e.target.value)}
              rows={12}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-xs leading-relaxed dark:border-slate-700 dark:bg-slate-950"
            />
          </label>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="font-semibold text-slate-900 dark:text-slate-100">2. Candidates</h2>
          <div className="mt-3 grid grid-cols-2 gap-2" role="radiogroup" aria-label="Candidate source">
            {(["samples", "upload"] as const).map((s) => (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={source === s}
                onClick={() => setSource(s)}
                className={`rounded-lg border px-3 py-2 text-sm font-medium ${
                  source === s
                    ? "border-indigo-600 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-950 dark:text-indigo-200"
                    : "border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}
              >
                {s === "samples" ? `Use ${samples.resumes.length} sample resumes` : "Upload resumes"}
              </button>
            ))}
          </div>

          {source === "samples" ? (
            <div className="mt-4 text-sm text-slate-600 dark:text-slate-300">
              <p>Fictional candidates, each designed to test something hard:</p>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                <li>a PH-style resume listing birthdate, civil status and religion</li>
                <li>overlapping jobs, a career gap, messy formatting</li>
                <li>a resume with a hidden instruction to inflate its seniority</li>
                <li>non-engineers (a recruiter, a designer) to test relevance</li>
              </ul>
            </div>
          ) : (
            <label className="mt-4 block rounded-lg border-2 border-dashed border-slate-300 p-6 text-center text-sm text-slate-600 hover:border-indigo-400 dark:border-slate-700 dark:text-slate-300">
              <input
                type="file"
                multiple
                accept=".pdf,.txt,application/pdf,text/plain"
                onChange={(e) => pickFiles(e.target.files)}
                className="sr-only"
              />
              <span className="font-medium text-indigo-600 dark:text-indigo-400">Choose files</span> — up to{" "}
              {MAX_FILES} PDF or .txt resumes
              {files.length > 0 && (
                <ul className="mt-3 space-y-0.5 text-left text-xs text-slate-500">
                  {files.map((f) => (
                    <li key={f.name + f.size}>{f.name}</li>
                  ))}
                </ul>
              )}
            </label>
          )}
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
            Uploaded resumes are processed by an LLM provider and not stored by this demo. Please
            don&apos;t upload other people&apos;s resumes without their consent.
          </p>
        </section>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={run}
          disabled={loading || jobTooShort || noFiles}
          className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? `Screening… ${elapsed}s` : "Screen candidates"}
        </button>
        {loading && elapsed >= WAKE_UP_HINT_AFTER_S && (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            The free server sleeps when idle; the first request can take 30–60 s.
          </p>
        )}
        {jobTooShort && <p className="text-sm text-slate-500">The job posting is too short.</p>}
      </div>

      {error && (
        <div role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950 dark:text-rose-200">
          {error}
        </div>
      )}

      {result && <ResultView result={result} />}
      {/* keyed by run, so a new screen starts a fresh conversation */}
      {result && result.ranking.length > 0 && <AssistantPanel key={screenRun} screen={result} />}
    </div>
  );
}
