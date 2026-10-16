# Recruiting Copilot

**[Live demo](https://recruiting-copilot-1x9k.onrender.com/)**: upload a resume at
`POST /recruiting/parse-resume/file` → *Try it out*. (Free hosting: the first request after
idle can take ~30-60 s while the server wakes up.)

AI platform for recruiters: parses resumes into structured, validated candidate profiles,
with candidate–job matching and a recruiter agent on the roadmap.

Built with **FastAPI**, **Pydantic** and **Claude structured outputs**, with an eval suite
from day one.

```
  resume (text or PDF)
          │  POST /recruiting/parse-resume[/file]
          ▼
  FastAPI ── input validation (size, type)
          │
          ▼
  core.StructuredExtractor ──► Claude (structured outputs, schema = ResumeExtraction)
          │                        LLM extracts facts & dates
          ▼
  experience.py                   code computes years (overlaps counted once)
          │
          ▼
  ParsedResume { profile, total_years_experience, usage }

  evals/recruiting ── 8 targeted resumes ──► per-check accuracy · latency · tokens
```

## Screening: rank candidates against a job

`POST /recruiting/screen` takes one job posting and up to 10 resumes and returns a ranked
shortlist. The LLM parses the posting and the resumes; **code scores and ranks**, so results
are explainable and identical across models.

```
job posting ──LLM──► JobRequirements (must-haves, nice-to-haves, min years, level, flags)
resumes ─────LLM──► ParsedResume (profile, computed years, computed seniority)
                           │
                           ▼
        matching.py: required-skill coverage (50) · years (20) · seniority (15) · bonus (15)
        experience, seniority and bonus credited only in proportion to required-skill match
                           │
                           ▼
        ranking: all must-haves first, then score · matched/missing skills · reasons
```

**Fair by design:** scoring never uses name, school, location or photos. Requirements about
age, gender, civil status, height or appearance (common in PH job ads) are extracted into
`flagged_requirements` for the recruiter to review, never used as criteria.

Example from a real-style PH posting (`evals/recruiting/jobs/senior-fullstack-ph.txt`):

```
FLAGGED: "Female, 25-35 years old, single, with pleasing personality"
         "Height at least 5'2""   "Please attach a recent 2x2 photo with your resume."

1.  81  maria-ph-fullstack    7.42y  ALL MUST-HAVES
2.  31  aisha-overlapping     6.67y  missing React, Node.js, TypeScript
3.  31  kevin-messy-format    8.83y  missing Node.js, PostgreSQL, AWS
4.   0  patricia-recruiter    8.42y  missing all 5 (8 years as a recruiter earns nothing here)
```

### Screening eval

`python -m evals.recruiting.run_screen_eval` scores rankings for 4 jobs (full-stack PH,
Go backend, ML engineer, talent acquisition) over all 8 resumes against hand-graded relevance
labels (`evals/recruiting/screen_cases.json`), and runs a counterfactual fairness test: the
same resume with a different name (Maria → John) and a different school (PUP → Stanford) goes
through the full pipeline, LLM included, and must get an identical score.

| Date | Model | Correct #1 | NDCG@3 | Irrelevant < 20 | Must-have recall | Bias flags | Fairness | Runs |
|------|-------|-----------|--------|-----------------|------------------|------------|----------|------|
| 2026-10-16 | openai/gpt-4o-mini | 100% | 1.00 | 98.6% | 91.7% | 83.3% | 100% | 3 |
| 2026-10-16 | openai/gpt-4o-mini, after fixes | **100%** | **1.00** | **100%** | **100%** | **100%** | **100%** | 3 |

Fixes from the first run: generic suffixes ignored in skill matching ("Greenhouse ATS" =
"Greenhouse"), and flags quoted one requirement at a time (the model had flagged a legitimate
night-shift requirement together with age and gender). The irrelevant-score threshold was not
changed; a QA tester with 1 of 3 required ML skills scores 17-23 across runs, ranked below
the partial-fit candidate. 14 LLM calls per run.

**Known limitation:** skill matching is exact (with aliases such as Postgres → PostgreSQL), so
"recruitment software" doesn't match a resume describing an applicant tracking system.
Semantic matching (embeddings) is the next step.

## Project layout

```
app/
├── core/                 domain-agnostic: LLM extraction, errors, shared schemas
└── domains/
    └── recruiting/       resume schema, prompts, experience math, routes
evals/recruiting/         labeled resumes + scorer
tests/                    unit + API tests (no API key needed)
```

A new use case (support tickets, invoices, ...) is a new folder under `domains/` with its
own schema and prompts; `core/` is reused unchanged.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # then add your OPENROUTER_API_KEY (or switch to Anthropic)
uvicorn app.main:app --reload   # interactive docs at http://localhost:8000/docs
```

## Deploy (Render, free tier)

1. Render dashboard → **New → Blueprint** → select this repo (`render.yaml` configures it).
2. Enter `OPENROUTER_API_KEY` when prompted. Use a dedicated key with a credit limit.
3. The root URL opens the interactive demo (`/docs`).

The public demo is protected by rate limiting (`app/core/rate_limit.py`): 20 LLM requests
per visitor per hour and 500 per day overall, configurable via environment variables.
Free instances sleep when idle, so the first request after a while takes ~30-60 s.

## LLM providers

Set `LLM_PROVIDER` in `.env`:

| Provider | How the schema is enforced |
|---|---|
| `openrouter` (default): any model, one key | `json_schema` response format, routed only to providers that support it; validated locally with up to 3 attempts |
| `anthropic`: Claude direct | Native structured outputs (enforced server-side), effort control, refusal fallback |

`python -m scripts.openrouter_models [filter]` lists models that support structured
outputs, with live prices. Switching models is a one-line `.env` change, and the eval
compares them.

## Tests and evals

```bash
pytest                               # free, fast, no API key
python -m evals.recruiting.run_eval  # real Claude calls over evals/recruiting/
```

Each eval resume targets one failure mode:

| Case | What it tests |
|---|---|
| maria-ph-fullstack | PH-style resume with birthdate, civil status, religion — must not leak |
| juan-fresh-grad | Internship-only experience |
| aisha-overlapping-roles | Overlapping roles (naive sum: 8.75 yrs, correct: 6.67) |
| daniel-career-gap | Career break must not count as a role or as experience |
| kevin-messy-format | Lowercase one-liners, year-only dates, "now" |
| patricia-recruiter | Non-engineering role and domain skills |
| mark-prompt-injection | Embedded "rate as principal" instruction must be ignored |
| liza-no-email | Missing email must be null, not invented |

## Eval results

| Date | Model | Change | All checks | Years | Email | Skills recall | No leak | p50 latency |
|------|-------|--------|-----------|-------|-------|---------------|---------|-------------|
| 2026-10-14 | deepseek/deepseek-v4-flash | Baseline | 62.5% | 75% | 87.5% | 100% | 100% | 17.5 s |
| 2026-10-14 | deepseek/deepseek-v4-flash | Lenient date parsing, end date beats `is_current`, email validation | **100%** | 100% | 100% | 100% | 100% | 12.6 s |

**Stricter eval** (exact seniority against a written rubric, skills checked per list,
3 runs per model, mean and per-run range):

| Date | Model | All checks (mean) | Per run | Years | Seniority | Skill lists | p50 latency |
|------|-------|-------------------|---------|-------|-----------|-------------|-------------|
| 2026-10-14 | deepseek/deepseek-v4-flash | 45.8% | 37.5 / 50 / 50 | 91.7% | 45.8% | 91.7% | 14.4 s |
| 2026-10-14 | anthropic/claude-haiku-5.5 | **79.2%** | 75 / 75 / 87.5 | 100% | 79.2% | 100% | 5.3 s |
| 2026-10-16 | openai/gpt-4o-mini | 50.0% | 50 / 50 / 50 | 100% | 50.0% | 100% | 4.6 s |

GPT-4o mini got every factual field right in all runs; all of its misses are the same four
experienced candidates without "Senior" in their title, rated "mid".

**Seniority moved from the LLM into code** (`app/domains/recruiting/seniority.py`): the model
now reports facts with quoted evidence (owns outcomes, leads a team, senior title, ...) and
code applies the rubric using the computed years.

| Date | Model | All checks (mean) | Per run | Seniority | p50 latency | Cost / 1,000 resumes |
|------|-------|-------------------|---------|-----------|-------------|----------------------|
| 2026-10-16 | openai/gpt-4o-mini | 75.0% (was 50%) | 75 / 75 / 75 | 75% | 3.1 s | ~$0.35 |
| 2026-10-16 | anthropic/claude-haiku-5.5 | **100%** (was 79.2%) | 100 / 100 / 100 | 100% | 5.9 s | ~$0.85 |

GPT-4o mini's remaining misses: it reports "leads a team" for "Led rebuild of...", "Mentored
3 junior developers" and "On-call lead", despite the field description excluding those.

DeepSeek also showed failures code can't fix: an invented end date on a current role, a
career break extracted as a job, and one run returning no experience at all. Remaining
Haiku misses are seniority only (underrating senior candidates without "senior" titles).
Seniority labels follow `SENIORITY_RUBRIC` in `app/domains/recruiting/schemas.py`.

**What the baseline eval caught:** the model ignored the requested `YYYY-MM` format
(`"Mar 2020"`, `"Present"`), marked an ended job as current, and put a portfolio URL in the
email field. All three were fixed in code rather than in the prompt, so the fixes hold
across models.

## Design decisions

- **The LLM extracts, code computes.** Claude extracts role dates; Python computes years of
  experience, merging overlapping roles and skipping gaps. LLMs are unreliable at date math,
  and a prompt-injected resume can't inflate the number.
- **Fair-hiring by design.** The output schema has no fields for age, gender, civil status,
  religion or photos, the prompt forbids using them, and the eval checks for leaks.
- **Structured outputs, not prompt-and-pray JSON.** The schema is sent with every request,
  and every response is validated against the same Pydantic model before it's used.
- **Provider-agnostic core.** Domains depend on an `Extractor` interface; OpenRouter and
  Anthropic are interchangeable implementations, so models are chosen by eval results.
- **Resumes are untrusted input.** The prompt treats embedded instructions as data, and an
  eval case checks it.
- **Errors mapped by retryability.** Rate limit → 429, upstream failures → 502/503,
  refusal → 422, handled once in `core/errors.py` for every domain.

## Roadmap

- [ ] Deploy with a live demo link
- [ ] Candidate ↔ job matching: hybrid search (BM25 + pgvector), reranking, precision@k evals
- [ ] Fairness eval: identical resumes with swapped names/schools must score the same
- [ ] Recruiter agent: drafts outreach and screening questions, recruiter approves before sending
- [ ] Next.js recruiter dashboard
