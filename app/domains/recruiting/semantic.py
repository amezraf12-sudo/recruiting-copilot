"""Semantic skill suggestions: retrieve with embeddings, check with the LLM.

Only skills that exact/alias matching missed get here. For each, the most similar resume
phrase is proposed if it clears SIMILARITY_THRESHOLD, then one LLM call per candidate
checks all of that candidate's proposals. Embeddings alone are not trusted: in the
skill-matching eval they scored AWS vs Azure (0.71) above real matches.

Results are suggestions for recruiter review, not score inputs: the LLM check gave
different verdicts for the same resume across runs (see matching.score_candidate).
"""

import asyncio
from dataclasses import dataclass

from app.core.embeddings import Embedder, cosine
from app.core.errors import LLMIncompleteError, LLMRefusalError
from app.core.llm import Extractor
from app.core.schemas import UsageInfo
from app.domains.recruiting.schemas import JobRequirements, ParsedResume
from app.domains.recruiting.skill_verifier import verify_pairs
from app.domains.recruiting.skills import candidate_phrases, candidate_skill_keys, has_skill

# Chosen on the train half of evals/recruiting/skill_pairs.json (lowest threshold with full
# recall there); proposals below it are never sent for verification.
SIMILARITY_THRESHOLD = 0.325

# Seen in the screening eval: nearly every wrong semantic match was a named tool matched to
# something merely related ("Node.js" via "Backend Engineer", "PostgreSQL" via "SQL",
# "CI/CD" via "Docker"), while correct ones were multi-word capabilities ("HR or recruitment
# software", "backend engineering"). So named tools must match exactly or by alias.
MIN_WORDS_FOR_SEMANTIC = 2


def eligible_for_semantic(skill: str) -> bool:
    return len(skill.split()) >= MIN_WORDS_FOR_SEMANTIC


@dataclass
class SemanticResult:
    # candidate id -> {required skill: resume phrase that demonstrates it}
    matches: dict[str, dict[str, str]]
    llm_usages: list[UsageInfo]
    embedding_tokens: int


async def find_semantic_matches(
    embedder: Embedder,
    extractor: Extractor,
    job: JobRequirements,
    resumes: dict[str, ParsedResume],
    max_concurrent: int = 4,
) -> SemanticResult:
    skills = [s for s in job.must_have_skills + job.nice_to_have_skills if eligible_for_semantic(s)]
    unmatched: dict[str, list[str]] = {}
    phrases: dict[str, list[str]] = {}
    for cid, resume in resumes.items():
        keys = candidate_skill_keys(resume.profile)
        missing = [s for s in skills if not has_skill(resume.profile, s, keys)]
        if missing:
            unmatched[cid] = missing
            phrases[cid] = candidate_phrases(resume.profile)

    if not unmatched:
        return SemanticResult({}, [], 0)

    tokens_before = embedder.tokens_used
    all_texts = [s for m in unmatched.values() for s in m] + [p for ps in phrases.values() for p in ps]
    vectors = await embedder.embed(all_texts)

    proposals: dict[str, list[tuple[str, str]]] = {}
    for cid, missing in unmatched.items():
        for skill in missing:
            best = max(phrases[cid], key=lambda p: cosine(vectors[skill], vectors[p]), default=None)
            if best and cosine(vectors[skill], vectors[best]) >= SIMILARITY_THRESHOLD:
                proposals.setdefault(cid, []).append((skill, best))

    sem = asyncio.Semaphore(max_concurrent)

    async def verify(cid: str):
        async with sem:
            try:
                verdicts, usage = await verify_pairs(extractor, proposals[cid])
                return cid, verdicts, usage
            except (LLMRefusalError, LLMIncompleteError):
                return cid, [False] * len(proposals[cid]), None  # unverified = not matched

    matches: dict[str, dict[str, str]] = {}
    usages: list[UsageInfo] = []
    for cid, verdicts, usage in await asyncio.gather(*(verify(c) for c in proposals)):
        if usage:
            usages.append(usage)
        verified = {skill: phrase for (skill, phrase), ok in zip(proposals[cid], verdicts) if ok}
        if verified:
            matches[cid] = verified

    return SemanticResult(matches, usages, embedder.tokens_used - tokens_before)
