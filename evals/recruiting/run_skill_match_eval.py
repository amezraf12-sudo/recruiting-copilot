"""Skill-matching eval: exact matching vs. exact + embedding similarity.

The threshold is chosen on the train half of skill_pairs.json and reported on the test
half, so the headline number isn't fitted to the data it's measured on. Usage:
    python -m evals.recruiting.run_skill_match_eval
    python -m evals.recruiting.run_skill_match_eval --model openai/text-embedding-3-large
"""

import argparse
import asyncio
import json
from pathlib import Path

from app import config
from app.core.embeddings import Embedder, cosine
from app.core.llm import create_extractor
from app.domains.recruiting.semantic import eligible_for_semantic
from app.domains.recruiting.skill_verifier import verify_pairs
from app.domains.recruiting.skills import exact_match

EVAL_DIR = Path(__file__).parent
VERIFY_BATCH = 8  # similar to the unmatched skills of one candidate in a real screen
THRESHOLDS = [round(0.30 + 0.025 * i, 3) for i in range(21)]  # 0.30 .. 0.80


def split(pairs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Deterministic 50/50 split that keeps positives and negatives balanced."""
    train, test = [], []
    for label in (True, False):
        group = [p for p in pairs if p["match"] is label]
        train += group[0::2]
        test += group[1::2]
    return train, test


def metrics(pairs: list[dict], predict) -> dict:
    tp = sum(predict(p) and p["match"] for p in pairs)
    fp = sum(predict(p) and not p["match"] for p in pairs)
    fn = sum(not predict(p) and p["match"] for p in pairs)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
            "false_matches": fp, "missed": fn}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="embedding model (default from config)")
    parser.add_argument("--verify", action="store_true", help="also test LLM verification")
    parser.add_argument("--llm", help="verifier LLM (default OPENROUTER_MODEL from .env)")
    args = parser.parse_args()
    if args.llm:
        config.OPENROUTER_MODEL = args.llm

    pairs = json.loads((EVAL_DIR / "skill_pairs.json").read_text(encoding="utf-8"))["pairs"]
    embedder = Embedder(model=args.model)
    try:
        vectors = await embedder.embed([p["job"] for p in pairs] + [p["candidate"] for p in pairs])
    finally:
        await embedder.aclose()
    for p in pairs:
        p["exact"] = exact_match(p["job"], p["candidate"])
        p["similarity"] = round(cosine(vectors[p["job"]], vectors[p["candidate"]]), 3)

    train, test = split(pairs)

    def hybrid(threshold):
        return lambda p: p["exact"] or p["similarity"] >= threshold

    # Best F1 on train; ties go to the higher threshold (fewer false matches).
    sweep = [(t, metrics(train, hybrid(t))) for t in THRESHOLDS]
    best_t, _ = max(sweep, key=lambda s: (s[1]["f1"], s[0]))

    report = {
        "embedding_model": embedder.model,
        "pairs": {"train": len(train), "test": len(test)},
        "embedding_tokens": embedder.tokens_used,
        "chosen_threshold": best_t,
        "test_exact_only": metrics(test, lambda p: p["exact"]),
        "test_exact_plus_embeddings": metrics(test, hybrid(best_t)),
    }

    if args.verify:
        # Retrieve-then-verify, as the product runs it: only multi-word capability skills are
        # eligible, embeddings propose (similarity >= threshold), the LLM decides.
        proposed = [p for p in pairs if not p["exact"] and eligible_for_semantic(p["job"])
                    and p["similarity"] >= best_t]
        extractor = create_extractor(cache=False)
        try:
            verdicts = []
            for i in range(0, len(proposed), VERIFY_BATCH):
                batch = proposed[i : i + VERIFY_BATCH]
                batch_verdicts, _ = await verify_pairs(
                    extractor, [(p["job"], p["candidate"]) for p in batch])
                verdicts += batch_verdicts
        finally:
            await extractor.aclose()
        for p, ok in zip(proposed, verdicts):
            p["verified"] = ok
        report["verifier_model"] = config.OPENROUTER_MODEL
        report["verifier_calls"] = -(-len(proposed) // VERIFY_BATCH)
        report["test_retrieve_then_verify"] = metrics(
            test, lambda p: p["exact"] or p.get("verified", False))
    print(json.dumps(report, indent=2))

    print("\nThreshold sweep on train (precision / recall / f1):")
    for t, m in sweep:
        marker = "  <- chosen" if t == best_t else ""
        print(f"  {t:.3f}  {m['precision']:.2f} / {m['recall']:.2f} / {m['f1']:.2f}{marker}")

    print("\nAll pairs by similarity (exact match marked *):")
    for p in sorted(pairs, key=lambda p: -p["similarity"]):
        label = "MATCH   " if p["match"] else "no-match"
        verdict = {True: " verified:yes", False: " verified:no"}.get(p.get("verified"), "")
        wrong = " <- WRONG" if "verified" in p and p["verified"] != p["match"] else ""
        print(f"  {p['similarity']:.3f}{'*' if p['exact'] else ' '} {label}  "
              f"{p['job']!r} vs {p['candidate'][:50]!r}{verdict}{wrong}")

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "skill-match-latest.json").write_text(
        json.dumps({"report": report, "pairs": pairs}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
