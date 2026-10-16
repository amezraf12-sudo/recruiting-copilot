import { Screener } from "@/components/Screener";
import { API_URL } from "@/lib/api";

const REPO_URL = "https://github.com/amezraf12-sudo/recruiting-copilot";

export default function Home() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Recruiting Copilot
          </h1>
          <nav className="flex gap-4 text-sm font-medium text-indigo-600 dark:text-indigo-400">
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:underline">
              GitHub
            </a>
            <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="hover:underline">
              API docs
            </a>
          </nav>
        </div>
        <p className="mt-2 max-w-2xl text-slate-600 dark:text-slate-300">
          Rank resumes against a job posting with explainable scores — and catch biased
          requirements before they reach your shortlist.
        </p>
      </header>

      <main>
        <Screener />
      </main>

      <footer className="mt-12 border-t border-slate-200 pt-6 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-400">
        <h2 className="font-semibold text-slate-900 dark:text-slate-200">How it works</h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5">
          <li>An LLM turns the job posting and each resume into structured data.</li>
          <li>
            Code — not the LLM — scores every candidate from required skills, years of experience
            and seniority, so the same resume always gets the same score.
          </li>
          <li>
            Name, school, location and photos are never used. Requirements about age, gender,
            civil status or appearance are flagged instead of applied.
          </li>
          <li>
            Skills written in other words are surfaced as suggestions for you to review, with the
            resume text as evidence.
          </li>
        </ol>
        <p className="mt-4">
          Accuracy and fairness are measured by eval suites in the{" "}
          <a href={REPO_URL} className="text-indigo-600 hover:underline dark:text-indigo-400">
            repository
          </a>
          .
        </p>
      </footer>
    </div>
  );
}
