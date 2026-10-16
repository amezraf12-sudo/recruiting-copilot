"""Deterministic candidate scoring against job requirements.

The LLM parses resumes and job postings; this module decides the ranking, so scores are
consistent, explainable and identical across models.

Scoring uses only skills, years of experience and seniority. Name, education, school,
location and anything in JobRequirements.flagged_requirements are never inputs.
"""

from app.domains.recruiting.schemas import (
    SENIORITY_ORDER,
    CandidateMatch,
    JobRequirements,
    ParsedResume,
    SemanticEvidence,
)
from app.domains.recruiting.skills import candidate_skill_keys, has_skill

# Relative weights; components that don't apply to a job (e.g. no nice-to-haves listed)
# drop out and the rest are re-normalized, so every score is on the same 0-100 scale.
WEIGHTS = {"must_have": 50, "years": 20, "seniority": 15, "nice_to_have": 15}


def _seniority_fit(candidate: str, target: str) -> float:
    gap = SENIORITY_ORDER.index(candidate) - SENIORITY_ORDER.index(target)
    if gap == 0:
        return 1.0
    if abs(gap) == 1:
        return 0.5
    return 0.0


def score_candidate(
    candidate_id: str,
    resume: ParsedResume,
    job: JobRequirements,
    suggestions: dict[str, str] | None = None,
) -> CandidateMatch:
    """suggestions: {skill: resume phrase} from semantic.py, attached for recruiter review.

    Suggestions never change the score. In evals, LLM verification of semantic matches gave
    different verdicts for the same resume across runs, so counting them made scores
    inconsistent (fairness check fell from 100% to 67%).
    """
    profile = resume.profile
    keys = candidate_skill_keys(profile)
    matched_must = [s for s in job.must_have_skills if has_skill(profile, s, keys)]
    missing_must = [s for s in job.must_have_skills if s not in matched_must]
    matched_nice = [s for s in job.nice_to_have_skills if has_skill(profile, s, keys)]
    years = resume.total_years_experience
    unmatched = missing_must + [s for s in job.nice_to_have_skills if s not in matched_nice]
    suggested = [
        SemanticEvidence(skill=s, evidence=(suggestions or {})[s])
        for s in unmatched
        if s in (suggestions or {})
    ]

    components: dict[str, float] = {}
    reasons: list[str] = []

    # Everything beyond required skills counts only as far as the candidate is relevant:
    # 8 years as a recruiter shouldn't earn points toward a developer role. Seen in a
    # screening run: candidates with zero required skills scored 35/100 from years and
    # seniority alone.
    relevance = 1.0
    if job.must_have_skills:
        relevance = len(matched_must) / len(job.must_have_skills)
        components["must_have"] = relevance
        reasons.append(f"Has {len(matched_must)}/{len(job.must_have_skills)} required skills.")
        if missing_must:
            reasons.append(f"Missing required: {', '.join(missing_must)}.")

    if job.min_years_experience:
        components["years"] = relevance * min(1.0, years / job.min_years_experience)
        verdict = "meets" if years >= job.min_years_experience else "below"
        reasons.append(
            f"{years:g} years of experience ({verdict} the {job.min_years_experience:g}+ required)."
        )

    if job.seniority:
        components["seniority"] = relevance * _seniority_fit(resume.seniority, job.seniority)
        if resume.seniority == job.seniority:
            reasons.append(f"Seniority matches ({resume.seniority}).")
        else:
            reasons.append(f"Seniority is {resume.seniority}; role targets {job.seniority}.")

    if relevance < 1 and len(components) > 1:
        reasons.append(
            f"Experience, seniority and bonus skills credited at {relevance:.0%}, matching "
            "required-skill coverage."
        )

    if job.nice_to_have_skills:
        components["nice_to_have"] = relevance * len(matched_nice) / len(job.nice_to_have_skills)
        if matched_nice:
            reasons.append(f"Nice-to-haves: {', '.join(matched_nice)}.")

    for s in suggested:
        reasons.append(f"Review: may have {s.skill!r} (via {s.evidence!r}); not scored.")

    total_weight = sum(WEIGHTS[name] for name in components)
    score = (
        round(100 * sum(WEIGHTS[name] * value for name, value in components.items()) / total_weight)
        if total_weight
        else 0
    )

    return CandidateMatch(
        candidate_id=candidate_id,
        full_name=profile.full_name,
        score=score,
        meets_all_must_haves=not missing_must,
        matched_must_haves=matched_must,
        missing_must_haves=missing_must,
        matched_nice_to_haves=matched_nice,
        suggested_matches=suggested,
        total_years_experience=years,
        seniority=resume.seniority,
        reasons=reasons,
    )


def rank(matches: list[CandidateMatch]) -> list[CandidateMatch]:
    """Candidates with every must-have first, then by score; ties keep input order."""
    return sorted(matches, key=lambda m: (not m.meets_all_must_haves, -m.score))
