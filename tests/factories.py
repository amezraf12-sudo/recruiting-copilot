"""Builders for test data, so tests only spell out the fields they care about."""

from app.domains.recruiting.schemas import (
    JobRequirements,
    ParsedResume,
    ResumeExtraction,
    SenioritySignals,
    WorkExperience,
)
from app.core.schemas import UsageInfo

USAGE = UsageInfo(model="fake", input_tokens=10, output_tokens=20, latency_ms=5)


def signals(**true_flags) -> SenioritySignals:
    flags = dict.fromkeys(
        ["is_student", "has_senior_title", "owns_outcomes", "leads_team", "org_level_scope"], False
    )
    return SenioritySignals(**(flags | true_flags), evidence=[])


def profile(
    name="Maria Santos", technical=(), soft=(), highlights=(), title="Developer", **overrides
) -> ResumeExtraction:
    fields = dict(
        full_name=name, email=None, phone=None, location=None, links=[], headline="Developer.",
        seniority_signals=signals(), technical_skills=list(technical), soft_skills=list(soft),
        experience=[WorkExperience(
            company="Co", title=title, start_date="2020-01", end_date=None, is_current=True,
            highlights=list(highlights),
        )],
        education=[], certifications=[], languages=[],
    )
    return ResumeExtraction(**(fields | overrides))


def parsed(profile_: ResumeExtraction, years=5.0, seniority="senior") -> ParsedResume:
    return ParsedResume(
        profile=profile_, total_years_experience=years, seniority=seniority, usage=USAGE
    )


def job(must=(), nice=(), min_years=None, seniority=None, **overrides) -> JobRequirements:
    fields = dict(
        title="Backend Engineer", seniority=seniority, min_years_experience=min_years,
        must_have_skills=list(must), nice_to_have_skills=list(nice), responsibilities=[],
        location=None, work_arrangement=None, flagged_requirements=[],
    )
    return JobRequirements(**(fields | overrides))
