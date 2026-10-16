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
from app.core.embeddings import Embedder
from app.core.llm import create_extractor
from app.domains.recruiting.matching import rank, score_candidate
from app.domains.recruiting.semantic import find_semantic_matches
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


async def run_once(extractor, spec: dict, embedder: Embedder | None) -> dict:
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

    usages = [p.usage for p in parsed]
    embedding_tokens = 0

    async def semantic_for(req, pool: dict) -> dict:
        """Same semantic pass the /screen endpoint runs; {} when disabled."""
        nonlocal embedding_tokens
        if embedder is None:
            return {}
        result = await find_semantic_matches(embedder, extractor, req, pool)
        usages.extend(result.llm_usages)
        embedding_tokens += result.embedding_tokens
        return result.matches

    per_job = []
    for case in spec["jobs"]:
        req = jobs[case["id"]].requirements
        semantic = await semantic_for(req, resumes)
        ranking = rank([score_candidate(rid, resumes[rid], req, semantic.get(rid)) for rid in resume_ids])
        ranked_ids = [m.candidate_id for m in ranking]
        relevance = case["relevance"]
        strong = {c for c, g in relevance.items() if g == 2}
        strong_complete = [m.meets_all_must_haves for m in ranking if m.candidate_id in strong]
        # Suggestions: helpful if they cover strong candidates' gaps, noise if on grade-0 ones.
        strong_gaps = [(m, s) for m in ranking if m.candidate_id in strong for s in m.missing_must_haves]
        covered = sum(any(x.skill == s for x in m.suggested_matches) for m, s in strong_gaps)
        noise = sum(len(m.suggested_matches) for m in ranking if relevance.get(m.candidate_id, 0) == 0)
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
            "strong_meet_all_must_haves": all(strong_complete),
            "strong_gaps": len(strong_gaps),
            "strong_gaps_suggested": covered,
            "suggestions_on_irrelevant": noise,
            "ranking": [(m.candidate_id, m.score) for m in ranking],
            "suggested_matches": {m.candidate_id: [(s.skill, s.evidence) for s in m.suggested_matches]
                                  for m in ranking if m.suggested_matches},
            "missing_for_strong": {m.candidate_id: m.missing_must_haves
                                   for m in ranking if m.candidate_id in strong and m.missing_must_haves},
            "parsed_must_haves": req.must_have_skills,
            "flagged": req.flagged_requirements,
        })

    fair_req = jobs[fair["job"]].requirements
    fair_pool = {"base": resumes[fair["base"]], **variants}
    fair_semantic = await semantic_for(fair_req, fair_pool)
    scores = {k: score_candidate(k, r, fair_req, fair_semantic.get(k)).score for k, r in fair_pool.items()}
    fairness = {name: {"score": scores[name], "base": scores["base"]} for name in variant_ids}

    return {
        "per_job": per_job,
        "fairness": fairness,
        "llm_calls": len(usages),
        "embedding_tokens": embedding_tokens,
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
        "strong_meet_all_must_haves_pct": round(
            100 * sum(j["strong_meet_all_must_haves"] for j in jobs) / len(jobs), 1),
        # None when strong candidates had no gaps at all (nothing to suggest), not 0%.
        "strong_gaps_suggested_pct": round(
            100 * sum(j["strong_gaps_suggested"] for j in jobs) / sum(j["strong_gaps"] for j in jobs), 1)
        if sum(j["strong_gaps"] for j in jobs) else None,
        "suggestions_on_irrelevant": sum(j["suggestions_on_irrelevant"] for j in jobs),
        "fairness_identical_pct": round(
            100 * sum(f["score"] == f["base"] for f in run["fairness"].values()) / len(run["fairness"]), 1),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="repeat the eval N times")
    parser.add_argument("--model", help="override the model from .env for this run")
    parser.add_argument("--no-semantic", action="store_true", help="exact skill matching only")
    args = parser.parse_args()
    if args.model:  # read at call time by the extractor, so overriding config works
        if config.LLM_PROVIDER == "openrouter":
            config.OPENROUTER_MODEL = args.model
        else:
            config.CLAUDE_MODEL = args.model

    spec = json.loads((EVAL_DIR / "screen_cases.json").read_text(encoding="utf-8"))
    extractor = create_extractor()
    embedder = None if args.no_semantic else Embedder()
    try:
        runs = [await run_once(extractor, spec, embedder) for _ in range(args.runs)]
    finally:
        await extractor.aclose()
        if embedder:
            await embedder.aclose()

    per_run = [summarize(r) for r in runs]
    summary = {
        "provider": config.LLM_PROVIDER,
        "model": runs[0]["model"],
        "semantic_matching": embedder is not None,
        "runs": args.runs,
        "llm_calls_per_run": round(statistics.mean(r["llm_calls"] for r in runs), 1),
        "embedding_tokens_per_run": round(statistics.mean(r["embedding_tokens"] for r in runs)),
        **{k: round(statistics.mean(vals), 3) if (vals := [s[k] for s in per_run if s[k] is not None])
           else None for k in per_run[0]},
        "top1_correct_pct_per_run": [s["top1_correct_pct"] for s in per_run],
    }
    print(json.dumps(summary, indent=2))

    spec_relevance = {j["id"]: j["relevance"] for j in spec["jobs"]}
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
            if j["missing_for_strong"]:
                problems.append(f"strong fit missing {j['missing_for_strong']}")
            top3 = ", ".join(f"{c} {s}" for c, s in j["ranking"][:3])
            print(f"  [run {i}] {j['job']:20} ndcg@{NDCG_K}={j[f'ndcg@{NDCG_K}']:.2f} "
                  f"top3: {top3}{'  <- ' + '; '.join(problems) if problems else ''}")
            for cid, found in j["suggested_matches"].items():
                grade = spec_relevance[j["job"]].get(cid, 0)
                for skill, evidence in found:
                    print(f"           suggest (grade {grade}): {cid}: {skill!r} via {evidence[:55]!r}")
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
