"""Screening eval: does the ranking put the right candidates on top, fairly?

Each resume is parsed once and scored against every job in jobs/, so a run costs
(jobs + resumes + fairness variants) LLM calls. Usage, from the project root:
    python -m evals.recruiting.run_screen_eval
    python -m evals.recruiting.run_screen_eval --runs 3 --model anthropic/claude-haiku-5.5
"""

import argparse
import asyncio
import json
import math
import statistics
from datetime import date, datetime
from pathlib import Path

from app import config
from app.core.llm import create_extractor
from app.domains.recruiting.matching import rank, score_candidate
from app.domains.recruiting.service import parse_job, parse_resume
from app.domains.recruiting.skills import skill_key

EVAL_DIR = Path(__file__).parent
NDCG_K = 3
IRRELEVANT_MAX_SCORE = 20  # grade-0 candidates should score below this


def ndcg(ranked_ids: list[str], relevance: dict[str, int], k: int) -> float:
    def dcg(grades: list[int]) -> float:
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:k]))

    ideal = dcg(sorted(relevance.values(), reverse=True))
    return dcg([relevance.get(c, 0) for c in ranked_ids]) / ideal if ideal else 1.0


async def run_once(extractor, spec: dict) -> dict:
    as_of = date.fromisoformat(spec["as_of"])
    sem = asyncio.Semaphore(4)

    async def limited(coro):
        async with sem:
            return await coro

    resume_texts = {p.stem: p.read_text(encoding="utf-8") for p in (EVAL_DIR / "resumes").glob("*.txt")}
    job_texts = {j["id"]: (EVAL_DIR / "jobs" / f"{j['id']}.txt").read_text(encoding="utf-8")
                 for j in spec["jobs"]}
    fair = spec["fairness"]
    variant_texts = {}
    for name, replacements in fair["variants"].items():
        text = resume_texts[fair["base"]]
        for old, new in replacements.items():
            assert old in text, f"fairness variant {name}: {old!r} not found in base resume"
            text = text.replace(old, new)
        variant_texts[name] = text

    job_ids, resume_ids, variant_ids = list(job_texts), list(resume_texts), list(variant_texts)
    parsed = await asyncio.gather(
        *(limited(parse_job(extractor, text=job_texts[j])) for j in job_ids),
        *(limited(parse_resume(extractor, text=resume_texts[r], as_of=as_of)) for r in resume_ids),
        *(limited(parse_resume(extractor, text=variant_texts[v], as_of=as_of)) for v in variant_ids),
    )
    jobs = dict(zip(job_ids, parsed[: len(job_ids)]))
    resumes = dict(zip(resume_ids, parsed[len(job_ids): len(job_ids) + len(resume_ids)]))
    variants = dict(zip(variant_ids, parsed[len(job_ids) + len(resume_ids):]))

    per_job = []
    for case in spec["jobs"]:
        req = jobs[case["id"]].requirements
        ranking = rank([score_candidate(rid, resumes[rid], req) for rid in resume_ids])
        ranked_ids = [m.candidate_id for m in ranking]
        relevance = case["relevance"]
        strong = {c for c, g in relevance.items() if g == 2}
        irrelevant = [m for m in ranking if relevance.get(m.candidate_id, 0) == 0]
        found = {skill_key(s) for s in req.must_have_skills}
        must_recall = sum(skill_key(s) in found for s in case["expected_must_haves"]) / len(
            case["expected_must_haves"])
        # Flags are checked by content, not count: every discriminatory term must be flagged,
        # and legitimate requirements (e.g. night shift) must not be.
        flagged_text = " ".join(req.flagged_requirements).lower()
        flags_ok = all(t.lower() in flagged_text for t in case["expected_flag_terms"]) and not any(
            t.lower() in flagged_text for t in case["must_not_flag"])
        per_job.append({
            "job": case["id"],
            "top1_correct": ranked_ids[0] in strong,
            f"ndcg@{NDCG_K}": round(ndcg(ranked_ids, relevance, NDCG_K), 3),
            "irrelevant_low_pct": round(
                100 * sum(m.score < IRRELEVANT_MAX_SCORE for m in irrelevant) / len(irrelevant), 1),
            "must_have_recall": round(must_recall, 3),
            "flags_found": flags_ok,
            "ranking": [(m.candidate_id, m.score) for m in ranking],
            "parsed_must_haves": req.must_have_skills,
            "flagged": req.flagged_requirements,
        })

    fair_req = jobs[fair["job"]].requirements
    base_score = score_candidate("base", resumes[fair["base"]], fair_req).score
    fairness = {
        name: {"score": score_candidate(name, variants[name], fair_req).score, "base": base_score}
        for name in variant_ids
    }

    usages = [p.usage for p in parsed]
    return {
        "per_job": per_job,
        "fairness": fairness,
        "llm_calls": len(usages),
        "model": usages[0].model,
        "input_tokens": sum(u.input_tokens for u in usages),
        "output_tokens": sum(u.output_tokens for u in usages),
    }


def summarize(run: dict) -> dict:
    jobs = run["per_job"]
    return {
        "top1_correct_pct": round(100 * sum(j["top1_correct"] for j in jobs) / len(jobs), 1),
        f"mean_ndcg@{NDCG_K}": round(statistics.mean(j[f"ndcg@{NDCG_K}"] for j in jobs), 3),
        "irrelevant_low_pct": round(statistics.mean(j["irrelevant_low_pct"] for j in jobs), 1),
        "must_have_recall_pct": round(100 * statistics.mean(j["must_have_recall"] for j in jobs), 1),
        "flags_found_pct": round(100 * sum(j["flags_found"] for j in jobs) / len(jobs), 1),
        "fairness_identical_pct": round(
            100 * sum(f["score"] == f["base"] for f in run["fairness"].values()) / len(run["fairness"]), 1),
    }


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

    spec = json.loads((EVAL_DIR / "screen_cases.json").read_text(encoding="utf-8"))
    extractor = create_extractor()
    try:
        runs = [await run_once(extractor, spec) for _ in range(args.runs)]
    finally:
        await extractor.aclose()

    per_run = [summarize(r) for r in runs]
    summary = {
        "provider": config.LLM_PROVIDER,
        "model": runs[0]["model"],
        "runs": args.runs,
        "llm_calls_per_run": runs[0]["llm_calls"],
        **{k: round(statistics.mean(s[k] for s in per_run), 3) for k in per_run[0]},
        "top1_correct_pct_per_run": [s["top1_correct_pct"] for s in per_run],
    }
    print(json.dumps(summary, indent=2))

    for i, run in enumerate(runs, start=1):
        for j in run["per_job"]:
            problems = []
            if not j["top1_correct"]:
                problems.append("wrong #1")
            if j["irrelevant_low_pct"] < 100:
                problems.append("irrelevant candidate scored high")
            if j["must_have_recall"] < 1:
                problems.append(f"must-haves parsed as {j['parsed_must_haves']}")
            if not j["flags_found"]:
                problems.append(f"flags: {j['flagged']}")
            top3 = ", ".join(f"{c} {s}" for c, s in j["ranking"][:3])
            print(f"  [run {i}] {j['job']:20} ndcg@{NDCG_K}={j[f'ndcg@{NDCG_K}']:.2f} "
                  f"top3: {top3}{'  <- ' + '; '.join(problems) if problems else ''}")
        for name, f in run["fairness"].items():
            if f["score"] != f["base"]:
                print(f"  [run {i}] FAIRNESS {name}: score {f['score']} vs base {f['base']}")

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"screen-{datetime.now():%Y%m%d-%H%M%S}.json"
    out_file.write_text(json.dumps({"summary": summary, "runs": runs}, indent=2), encoding="utf-8")
    print(f"\nSaved {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
