"use client";

import { useState } from "react";

import {
  ApiError,
  type AssistantResponse,
  type ChatMessage,
  type ScreenResult,
  askAssistant,
} from "@/lib/api";
import { ActionCard } from "./ActionCard";

const SUGGESTIONS = [
  "Draft an outreach email for everyone who meets all required skills.",
  "Write screening questions for the best candidate who's missing skills.",
  "Who has the most relevant experience, and why?",
];
const MAX_HISTORY = 19; // the API accepts 20 messages including the new one

type Turn = { role: "user"; content: string } | { role: "assistant"; response: AssistantResponse };

/** Replies are shown as plain text; drop markdown emphasis if the model adds it anyway. */
function plain(text: string) {
  return text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/^#+\s+/gm, "");
}

function formatArgs(args: Record<string, unknown>) {
  const shown = Object.entries(args)
    .filter(([k]) => k === "candidate_id")
    .map(([, v]) => String(v));
  return shown.join(", ");
}

export function AssistantPanel({ screen }: { screen: ScreenResult }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(text: string) {
    const content = text.trim();
    if (!content || loading) return;
    const history: ChatMessage[] = turns.map((t) =>
      t.role === "user" ? t : { role: "assistant", content: t.response.reply },
    );
    const messages = [...history.slice(-MAX_HISTORY), { role: "user" as const, content }];
    setTurns((prev) => [...prev, { role: "user", content }]);
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const response = await askAssistant(screen, messages);
      setTurns((prev) => [...prev, { role: "assistant", response }]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setTurns((prev) => prev.slice(0, -1)); // let the recruiter retry the same request
      setInput(content);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-5 dark:border-indigo-900 dark:bg-indigo-950/20">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Ask the assistant</h2>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        An AI agent that drafts outreach emails and screening questions from this shortlist.
        It only proposes; nothing is sent until you approve and copy it.
      </p>

      <div className="mt-4 space-y-4">
        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <div key={i} className="ml-auto max-w-[85%] rounded-xl bg-indigo-600 px-4 py-2 text-sm text-white">
              {turn.content}
            </div>
          ) : (
            <div key={i} className="space-y-3">
              <div className="max-w-[85%] whitespace-pre-line rounded-xl bg-white px-4 py-3 text-sm text-slate-800 shadow-sm dark:bg-slate-900 dark:text-slate-200">
                {plain(turn.response.reply)}
              </div>
              {turn.response.actions.map((a) => (
                <ActionCard key={`${i}-${a.id}`} action={a} />
              ))}
              {turn.response.trace.length > 0 && (
                <details className="text-xs text-slate-500 dark:text-slate-400">
                  <summary className="cursor-pointer select-none">
                    How I got this: {turn.response.trace.length} tool calls,{" "}
                    {turn.response.usage.llm_calls} model calls,{" "}
                    {(turn.response.usage.latency_ms / 1000).toFixed(1)} s
                  </summary>
                  <ol className="mt-2 list-decimal space-y-0.5 pl-5 font-mono">
                    {turn.response.trace.map((t, j) => (
                      <li key={j} className={t.ok ? "" : "text-rose-600"}>
                        {t.tool}({formatArgs(t.arguments)}){t.ok ? "" : " — error, retried"}
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          ),
        )}
        {loading && (
          <p className="text-sm text-slate-500 dark:text-slate-400" aria-live="polite">
            Working: looking up candidates and drafting…
          </p>
        )}
      </div>

      {turns.length === 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" onClick={() => send(s)} disabled={loading}
              className="rounded-full border border-indigo-200 bg-white px-3 py-1.5 text-left text-sm text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 dark:border-indigo-800 dark:bg-slate-900 dark:text-indigo-300">
              {s}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950 dark:text-rose-200">
          {error}
        </div>
      )}

      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <label htmlFor="assistant-input" className="sr-only">Message the assistant</label>
        <input
          id="assistant-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={4000}
          placeholder="e.g. Draft screening questions for Aisha"
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        <button type="submit" disabled={loading || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">
          Send
        </button>
      </form>
    </section>
  );
}
