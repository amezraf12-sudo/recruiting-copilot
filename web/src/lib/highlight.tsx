import type { ReactNode } from "react";

export type Highlight = { text: string; className: string; title?: string };

function escape(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Wrap every occurrence of the given terms in <mark>. Short terms (skills) match as whole
 * words, like the backend's skill matcher, so "Go" doesn't light up inside "Google".
 * Longer phrases (evidence sentences) match as plain substrings. Longest terms win.
 */
export function highlight(text: string, terms: Highlight[]): ReactNode[] {
  const usable = terms
    .filter((t) => t.text.trim().length > 0)
    .sort((a, b) => b.text.length - a.text.length);
  if (usable.length === 0) return [text];

  const pattern = usable
    .map((t) => (t.text.includes(" ") && t.text.length > 25
      ? escape(t.text)
      : `(?<![A-Za-z0-9])${escape(t.text)}(?![A-Za-z0-9])`))
    .join("|");
  const regex = new RegExp(pattern, "gi");
  const byLower = new Map(usable.map((t) => [t.text.toLowerCase(), t]));

  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(regex)) {
    const start = match.index ?? 0;
    if (start > last) out.push(text.slice(last, start));
    const term = byLower.get(match[0].toLowerCase());
    out.push(
      <mark key={start} title={term?.title} className={`rounded px-0.5 ${term?.className ?? ""}`}>
        {match[0]}
      </mark>,
    );
    last = start + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export const MARK = {
  required: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/60 dark:text-emerald-100",
  bonus: "bg-sky-100 text-sky-900 dark:bg-sky-900/60 dark:text-sky-100",
  review: "bg-amber-100 text-amber-900 dark:bg-amber-900/60 dark:text-amber-100",
};
