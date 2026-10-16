// Client for the Recruiting Copilot API. Types mirror app/domains/recruiting/schemas.py.

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "https://recruiting-copilot-1x9k.onrender.com"
).replace(/\/$/, "");

export type Seniority = "intern" | "junior" | "mid" | "senior" | "lead" | "principal";

export interface JobRequirements {
  title: string;
  seniority: Seniority | null;
  min_years_experience: number | null;
  must_have_skills: string[];
  nice_to_have_skills: string[];
  responsibilities: string[];
  location: string | null;
  work_arrangement: "onsite" | "hybrid" | "remote" | null;
  flagged_requirements: string[];
}

export interface SemanticEvidence {
  skill: string;
  evidence: string;
}

export interface CandidateMatch {
  candidate_id: string;
  full_name: string | null;
  score: number;
  meets_all_must_haves: boolean;
  matched_must_haves: string[];
  missing_must_haves: string[];
  matched_nice_to_haves: string[];
  suggested_matches: SemanticEvidence[];
  total_years_experience: number;
  seniority: Seniority;
  reasons: string[];
}

export interface ScreenResult {
  job: JobRequirements;
  ranking: CandidateMatch[];
  errors: { candidate_id: string; error: string }[];
  usage: {
    llm_calls: number;
    input_tokens: number;
    output_tokens: number;
    embedding_tokens: number;
    latency_ms: number;
  };
}

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    // FastAPI sends {"detail": "..."} or, for validation errors, {"detail": [{msg, ...}]}.
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // not JSON
  }
  return `Request failed (${response.status}).`;
}

async function post(path: string, init: RequestInit): Promise<ScreenResult> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { method: "POST", ...init });
  } catch {
    throw new ApiError(
      "Couldn't reach the API. The free server may be waking up (30-60 s) — please try again.",
    );
  }
  if (!response.ok) {
    const detail = await readError(response);
    if (response.status === 429) {
      throw new ApiError(`${detail} The public demo is rate limited to protect its budget.`, 429);
    }
    throw new ApiError(detail, response.status);
  }
  return response.json();
}

export function screenTexts(
  jobDescription: string,
  candidates: { id: string; text: string }[],
): Promise<ScreenResult> {
  return post("/recruiting/screen", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_description: jobDescription, candidates }),
  });
}

export function screenFiles(jobDescription: string, files: File[]): Promise<ScreenResult> {
  const form = new FormData();
  form.append("job_description", jobDescription);
  for (const file of files) form.append("files", file);
  return post("/recruiting/screen/upload", { body: form });
}
