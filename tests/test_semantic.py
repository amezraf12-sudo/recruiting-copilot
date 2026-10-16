"""Semantic matching with a fake embedder and fake verifier: no network, no key."""

import asyncio

from app.core.errors import LLMIncompleteError
from app.core.llm import ExtractionResult
from app.domains.recruiting.matching import score_candidate
from app.domains.recruiting.semantic import find_semantic_matches
from app.domains.recruiting.skill_verifier import SkillVerdict, SkillVerdicts
from tests.factories import USAGE, job, parsed, profile

ATS = "Led rebuild of the applicant tracking system"
# Unit vectors chosen so cosine similarity is exactly what each test needs.
VECTORS = {
    "recruitment software": [1.0, 0.0],
    ATS: [0.8, 0.6],              # cos 0.8 with "recruitment software"
    "Azure": [0.6, 0.8],          # cos 0.6 with "AWS" below: related, not equal
    "AWS": [1.0, 0.0],
    "Kubernetes": [0.0, 1.0],     # cos 0 with "recruitment software"
}


class FakeEmbedder:
    def __init__(self):
        self.tokens_used = 0
        self.requests: list[list[str]] = []

    async def embed(self, texts):
        self.requests.append(texts)
        self.tokens_used += len(texts)
        return {t: VECTORS.get(t, [0.0, 0.0]) for t in texts}


class FakeVerifier:
    """Accepts only the (skill, phrase) pairs in `accept`; records what it was asked."""

    def __init__(self, accept=(), error=None):
        self.accept, self.error = set(accept), error
        self.asked: list[list[str]] = []

    async def extract(self, *, text, **_):
        lines = text.splitlines()
        self.asked.append(lines)
        if self.error:
            raise self.error
        verdicts = [
            SkillVerdict(index=i, demonstrates=any(f'"{s}"' in line and f'"{p}"' in line
                                                   for s, p in self.accept), reason="")
            for i, line in enumerate(lines)
        ]
        return ExtractionResult(data=SkillVerdicts(verdicts=verdicts), usage=USAGE)


def run(requirements, resumes, verifier):
    return asyncio.run(find_semantic_matches(FakeEmbedder(), verifier, requirements, resumes))


def test_verified_semantic_match_is_returned_with_evidence():
    resumes = {"maria": parsed(profile(highlights=[ATS]))}
    verifier = FakeVerifier(accept=[("recruitment software", ATS)])
    result = run(job(must=["recruitment software"]), resumes, verifier)
    assert result.matches == {"maria": {"recruitment software": ATS}}
    assert len(result.llm_usages) == 1  # one verification call for the candidate


def test_named_tools_never_go_through_semantic_matching():
    # "AWS" vs "Azure" is related (cos 0.6) but a single-word tool: exact/alias only.
    resumes = {"c": parsed(profile(technical=["Azure"]))}
    verifier = FakeVerifier(accept=[("AWS", "Azure")])  # even a lenient verifier isn't asked
    result = run(job(must=["AWS"]), resumes, verifier)
    assert result.matches == {} and verifier.asked == [] and result.embedding_tokens == 0


def test_capability_rejected_by_verifier_is_not_matched():
    resumes = {"maria": parsed(profile(highlights=[ATS]))}
    verifier = FakeVerifier(accept=[])  # proposed (cos 0.8), then rejected
    assert run(job(must=["recruitment software"]), resumes, verifier).matches == {}
    assert len(verifier.asked) == 1


def test_low_similarity_is_never_sent_for_verification():
    resumes = {"c": parsed(profile(technical=["Kubernetes"]))}
    verifier = FakeVerifier()
    assert run(job(must=["recruitment software"]), resumes, verifier).matches == {}
    assert verifier.asked == []  # cos 0 < threshold: no LLM call spent


def test_exact_matches_skip_the_semantic_pass_entirely():
    resumes = {"c": parsed(profile(technical=["AWS"]))}
    verifier = FakeVerifier()
    result = run(job(must=["AWS"]), resumes, verifier)
    assert result.matches == {} and result.embedding_tokens == 0 and verifier.asked == []


def test_verifier_failure_means_no_match_not_a_crash():
    resumes = {"maria": parsed(profile(highlights=[ATS]))}
    verifier = FakeVerifier(error=LLMIncompleteError("bad output"))
    assert run(job(must=["recruitment software"]), resumes, verifier).matches == {}


def test_suggestions_are_shown_but_never_change_the_score():
    resume = parsed(profile(technical=["React"], highlights=[ATS]))
    requirements = job(must=["React", "recruitment software"])
    without = score_candidate("m", resume, requirements)
    with_suggestion = score_candidate("m", resume, requirements, {"recruitment software": ATS})
    assert without.score == with_suggestion.score == 50
    assert not with_suggestion.meets_all_must_haves  # ranking unchanged too
    assert with_suggestion.missing_must_haves == ["recruitment software"]
    assert with_suggestion.suggested_matches[0].evidence == ATS
    assert any("not scored" in r for r in with_suggestion.reasons)


def test_suggestions_for_already_matched_skills_are_dropped():
    resume = parsed(profile(technical=["React"]))
    m = score_candidate("m", resume, job(must=["React"]), {"React": "React apps"})
    assert m.suggested_matches == []
