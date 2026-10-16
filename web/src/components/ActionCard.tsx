"use client";

import { useState } from "react";

import type { ProposedAction } from "@/lib/api";
import { Chip } from "./Chip";

type Status = "pending" | "approved" | "rejected";

function asText(a: { subject: string; body: string; questions: string[] }, type: ProposedAction["type"]) {
  return type === "outreach_email"
    ? `Subject: ${a.subject}\n\n${a.body}`
    : a.questions.map((q, i) => `${i + 1}. ${q}`).join("\n");
}

/** One proposal from the assistant. Nothing is sent: approving unlocks copy-to-clipboard. */
export function ActionCard({ action }: { action: ProposedAction }) {
  const [status, setStatus] = useState<Status>("pending");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    subject: action.subject ?? "",
    body: action.body ?? "",
    questions: action.questions,
  });
  const [copied, setCopied] = useState(false);

  const isEmail = action.type === "outreach_email";
  const title = `${isEmail ? "Outreach email" : "Screening questions"} · ${action.candidate_name ?? action.candidate_id}`;

  async function copy() {
    await navigator.clipboard.writeText(asText(draft, action.type));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const field =
    "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950";

  return (
    <div
      className={`rounded-xl border p-4 ${
        status === "rejected"
          ? "border-slate-200 opacity-60 dark:border-slate-800"
          : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-semibold text-slate-900 dark:text-slate-100">{title}</h4>
        {status === "approved" && <Chip tone="match">Approved</Chip>}
        {status === "rejected" && <Chip tone="neutral">Rejected</Chip>}
        {status === "pending" && <Chip tone="review">Needs your review</Chip>}
      </div>

      {action.warnings.length > 0 && (
        <ul role="alert" className="mt-3 space-y-1 rounded-lg bg-rose-50 p-3 text-sm text-rose-900 dark:bg-rose-950/50 dark:text-rose-200">
          {action.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}

      {editing ? (
        <div className="mt-3 space-y-2">
          {isEmail ? (
            <>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-300">
                Subject
                <input className={field} value={draft.subject}
                  onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
              </label>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-300">
                Body
                <textarea className={field} rows={10} value={draft.body}
                  onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
              </label>
            </>
          ) : (
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300">
              Questions (one per line)
              <textarea className={field} rows={8} value={draft.questions.join("\n")}
                onChange={(e) => setDraft({ ...draft, questions: e.target.value.split("\n") })} />
            </label>
          )}
        </div>
      ) : isEmail ? (
        <div className="mt-3 text-sm text-slate-700 dark:text-slate-300">
          <p className="font-medium">Subject: {draft.subject}</p>
          <p className="mt-2 whitespace-pre-line">{draft.body}</p>
        </div>
      ) : (
        <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-slate-700 dark:text-slate-300">
          {draft.questions.filter((q) => q.trim()).map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ol>
      )}

      <div className="mt-4 flex flex-wrap gap-2 text-sm font-medium">
        {status !== "approved" && (
          <button type="button" onClick={() => { setStatus("approved"); setEditing(false); }}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-white hover:bg-emerald-500">
            Approve
          </button>
        )}
        {status === "approved" && (
          <button type="button" onClick={copy}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-white hover:bg-indigo-500">
            {copied ? "Copied" : "Copy to clipboard"}
          </button>
        )}
        <button type="button" onClick={() => { setEditing(!editing); setStatus("pending"); }}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">
          {editing ? "Done editing" : "Edit"}
        </button>
        {status !== "rejected" && (
          <button type="button" onClick={() => { setStatus("rejected"); setEditing(false); }}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">
            Reject
          </button>
        )}
      </div>
    </div>
  );
}
