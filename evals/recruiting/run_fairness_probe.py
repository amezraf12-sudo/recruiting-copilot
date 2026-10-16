"""Fairness probe: is a score difference between resume variants bias or run-to-run noise?

Parses the base resume and each counterfactual variant N times, scores them against the
fairness job, and reports the score distribution per variant plus which extracted fields
differ. If the base resume varies as much as the variants, the cause is nondeterminism,
not the swapped attribute. Usage, from the project root:
    python -m evals.recruiting.run_fairness_probe --n 5 --model anthropic/claude-haiku-5.5
"""

import argparse
import asyncio
import json
from collections import Counter
from datetime import date
from pathlib import Path

from app import config
from app.core.llm import create_extractor
from app.domains.recruiting.matching import score_candidate
from app.domains.recruiting.service import parse_job, parse_resume

EVAL_DIR = Path(__file__).parent


def fingerprint(resume, match) -> dict:
    """The parsed facts that feed the score."""
    p = resume.profile
    return {
        "years": resume.total_years_experience,
        "seniority": resume.seniority,
        "signals": tuple(k for k, v in p.seniority_signals.model_dump().items() if v is True),
        "matched_must": tuple(match.matched_must_haves),
        "matched_nice": tuple(match.matched_nice_to_haves),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.model:
        config.OPENROUTER_MODEL = args.model

    spec = json.loads((EVAL_DIR / "screen_cases.json").read_text(encoding="utf-8"))
    fair = spec["fairness"]
    as_of = date.fromisoformat(spec["as_of"])
    base_text = (EVAL_DIR / "resumes" / f"{fair['base']}.txt").read_text(encoding="utf-8")
    texts = {"base": base_text}
    for name, replacements in fair["variants"].items():
        text = base_text
        for old, new in replacements.items():
            text = text.replace(old, new)
        texts[name] = text

    extractor = create_extractor()
    sem = asyncio.Semaphore(4)

    async def parse(text):
        async with sem:
            return await parse_resume(extractor, text=text, as_of=as_of)

    try:
        job = await parse_job(extractor, text=(EVAL_DIR / "jobs" / f"{fair['job']}.txt").read_text(encoding="utf-8"))
        names = [n for n in texts for _ in range(args.n)]
        parsed = await asyncio.gather(*(parse(texts[n]) for n in names))
    finally:
        await extractor.aclose()

    req = job.requirements
    by_variant: dict[str, list] = {n: [] for n in texts}
    for name, resume in zip(names, parsed):
        match = score_candidate(name, resume, req)
        by_variant[name].append((match.score, fingerprint(resume, match)))

    print(f"model: {config.OPENROUTER_MODEL} | job: {fair['job']} | {args.n} parses per variant\n")
    for name, rows in by_variant.items():
        scores = Counter(s for s, _ in rows)
        print(f"{name:12} scores: {dict(sorted(scores.items()))}")
    print("\nDistinct parsed facts per variant (count x facts):")
    for name, rows in by_variant.items():
        for fp, count in Counter(json.dumps(fp, sort_keys=True) for _, fp in rows).most_common():
            print(f"  {name:12} {count}x {fp}")


if __name__ == "__main__":
    asyncio.run(main())
