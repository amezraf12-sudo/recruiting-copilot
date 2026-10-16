"""Resume-parser eval: run every resume in resumes/ against cases.json and score it.

Calls the configured LLM provider (costs money). Usage, from the project root:
    python -m evals.recruiting.run_eval                       # 1 run, model from .env
    python -m evals.recruiting.run_eval --runs 3              # repeat to measure variance
    python -m evals.recruiting.run_eval --model anthropic/claude-haiku-5.5
"""

import argparse
import asyncio
import json
import re
import statistics
from datetime import date, datetime
from pathlib import Path

from app import config
from app.core.llm import create_extractor
from app.domains.recruiting.schemas import ParsedResume
from app.domains.recruiting.service import parse_resume

EVAL_DIR = Path(__file__).parent
YEARS_TOLERANCE = 0.5
CHECKS = ["name", "email", "years", "seniority", "roles", "skills", "skill_lists", "no_leak"]


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def found_in(expected: list[str], extracted: list[str]) -> list[str]:
    extracted = [norm(s) for s in extracted]
    return [s for s in expected if any(norm(s) in x for x in extracted)]


def score(parsed: ParsedResume, exp: dict) -> dict:
    p = parsed.profile
    all_skills = p.technical_skills + p.soft_skills
    found = found_in(exp["skills"] + exp["soft_skills"], all_skills)
    # Right list: hard skills in technical_skills, interpersonal ones in soft_skills.
    misfiled = [s for s in exp["skills"] if s not in found_in(exp["skills"], p.technical_skills)]
    misfiled += [s for s in exp["soft_skills"] if s not in found_in(exp["soft_skills"], p.soft_skills)]
    profile_text = p.model_dump_json().lower()
    leaked = [s for s in exp["must_not_contain"] if s.lower() in profile_text]
    n_expected = len(exp["skills"]) + len(exp["soft_skills"])
    return {
        "checks": {
            "name": norm(p.full_name) == norm(exp["full_name"]),
            "email": p.email == exp["email"],
            "years": abs(parsed.total_years_experience - exp["years"]) <= YEARS_TOLERANCE,
            "seniority": parsed.seniority == exp["seniority"],
            "roles": len(p.experience) == exp["num_roles"],
            "skills": len(found) == n_expected,
            "skill_lists": not misfiled,
            "no_leak": not leaked,
        },
        "skill_recall": len(found) / n_expected,
        "detail": {
            "years": f"{parsed.total_years_experience} vs {exp['years']}",
            "seniority": f"{parsed.seniority} vs {exp['seniority']}",
            "signals": {k: v for k, v in p.seniority_signals.model_dump().items() if v is True},
            "roles": f"{len(p.experience)} vs {exp['num_roles']}",
            "missing_skills": [s for s in exp["skills"] + exp["soft_skills"] if s not in found],
            "misfiled_skills": misfiled,
            "leaked": leaked,
        },
    }


async def run_case(extractor, case: dict, as_of: date, sem: asyncio.Semaphore) -> dict:
    text = (EVAL_DIR / "resumes" / f"{case['id']}.txt").read_text(encoding="utf-8")
    async with sem:
        try:
            parsed = await parse_resume(extractor, text=text, as_of=as_of)
        except Exception as e:  # record failures instead of aborting the whole run
            return {"id": case["id"], "error": f"{type(e).__name__}: {e}"}
    return {"id": case["id"], **score(parsed, case["expected"]), "output": parsed.model_dump()}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if "error" not in r]
    n = len(ok) or 1
    usage = [r["output"]["usage"] for r in ok]
    return {
        "errors": len(results) - len(ok),
        "all_checks_pass_pct": round(100 * sum(all(r["checks"].values()) for r in ok) / n, 1),
        **{f"{c}_pct": round(100 * sum(r["checks"][c] for r in ok) / n, 1) for c in CHECKS},
        "skill_recall_pct": round(100 * sum(r["skill_recall"] for r in ok) / n, 1),
        "latency_ms_p50": int(statistics.median(u["latency_ms"] for u in usage)) if ok else None,
        "avg_output_tokens": int(statistics.mean(u["output_tokens"] for u in usage)) if ok else None,
    }


def print_failures(results: list[dict], run: int) -> None:
    for r in results:
        if "error" in r:
            print(f"  [run {run}] ERROR {r['id']}: {r['error']}")
            continue
        failed = [c for c, passed in r["checks"].items() if not passed]
        if failed:
            print(f"  [run {run}] FAIL  {r['id']}: {', '.join(failed)}  {r['detail']}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="repeat the eval N times")
    parser.add_argument("--model", help="override the model from .env for this run")
    args = parser.parse_args()
    if args.model:  # read at call time by the extractor, so overriding config works
        if config.LLM_PROVIDER == "openrouter":
            config.OPENROUTER_MODEL = args.model
        else:
            config.CLAUDE_MODEL = args.model

    spec = json.loads((EVAL_DIR / "cases.json").read_text(encoding="utf-8"))
    as_of = date.fromisoformat(spec["as_of"])  # fixed date keeps "Present" reproducible
    extractor = create_extractor(cache=False)
    sem = asyncio.Semaphore(4)
    runs: list[list[dict]] = []
    try:
        for _ in range(args.runs):
            runs.append(await asyncio.gather(*(run_case(extractor, c, as_of, sem) for c in spec["cases"])))
    finally:
        await extractor.aclose()

    per_run = [summarize(r) for r in runs]
    model = next((r["output"]["usage"]["model"] for run in runs for r in run if "output" in r), None)
    pct_keys = [k for k in per_run[0] if k.endswith("_pct")]
    latencies = [s["latency_ms_p50"] for s in per_run if s["latency_ms_p50"] is not None]
    out_tokens = [s["avg_output_tokens"] for s in per_run if s["avg_output_tokens"] is not None]
    summary = {
        "provider": config.LLM_PROVIDER,
        "model": model,
        "runs": args.runs,
        "cases_per_run": len(spec["cases"]),
        "errors": sum(s["errors"] for s in per_run),
        **{k: round(statistics.mean(s[k] for s in per_run), 1) for k in pct_keys},  # mean over runs
        "all_checks_pass_pct_per_run": [s["all_checks_pass_pct"] for s in per_run],
        "latency_ms_p50": int(statistics.median(latencies)) if latencies else None,
        "avg_output_tokens": int(statistics.mean(out_tokens)) if out_tokens else None,
    }

    print(json.dumps(summary, indent=2))
    for i, results in enumerate(runs, start=1):
        print_failures(results, i)

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out_file.write_text(json.dumps({"summary": summary, "runs": runs}, indent=2), encoding="utf-8")
    print(f"\nSaved {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
