import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import UsageInfo

Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal"]
SENIORITY_ORDER: list[str] = list(Seniority.__args__)

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# --- What the LLM must return (sent to Claude as a JSON schema) ---
# No validators like min_length here: structured outputs guarantee the shape,
# and field descriptions act as per-field instructions.
# Deliberately NO fields for age, birthdate, gender, civil status, religion or photo.
class WorkExperience(BaseModel):
    company: str
    title: str
    start_date: str | None = Field(
        description="YYYY-MM. If only a year is given, use YYYY-01. Null if unknown."
    )
    end_date: str | None = Field(
        description="YYYY-MM. If only a year is given, use YYYY-01. "
        "Null if this is the current role or the end is unknown."
    )
    is_current: bool = Field(description="True if the resume says Present/Current/Now.")
    highlights: list[str] = Field(description="Key achievements or responsibilities, concise.")


class Education(BaseModel):
    institution: str
    degree: str | None
    field_of_study: str | None
    graduation_year: int | None


class SenioritySignals(BaseModel):
    """Facts the LLM reports; seniority.py turns them (plus computed years) into a level."""

    is_student: bool = Field(
        description="Currently enrolled as a student, or only seeking an internship. "
        "False for graduates."
    )
    has_senior_title: bool = Field(
        description="Any role title says Senior, Sr., or an equivalent level (e.g. 'III')."
    )
    owns_outcomes: bool = Field(
        description="Owns something end to end: a service or system, a shared system "
        "others depend on, a full process (e.g. full-cycle recruiting), or mentors others."
    )
    leads_team: bool = Field(
        description="Has a lead/manager title, or explicitly leads or manages a team of "
        "people. Mentoring, leading a project, or leading an on-call rotation alone "
        "does not count."
    )
    org_level_scope: bool = Field(
        description="Sets direction across an organization: staff, principal, head-of, "
        "director or higher titles."
    )
    evidence: list[str] = Field(
        description="Short phrases quoted from the resume that support each signal "
        "set to true. Empty if all are false."
    )


class ResumeExtraction(BaseModel):
    full_name: str | None
    email: str | None = Field(description="An email address only. Null if the resume has none.")
    phone: str | None
    location: str | None = Field(description="City and/or country only.")
    links: list[str] = Field(description="LinkedIn, GitHub, portfolio URLs.")
    headline: str = Field(description="One neutral, factual line summarizing the candidate.")
    seniority_signals: SenioritySignals
    technical_skills: list[str] = Field(
        description="Hard skills: languages, frameworks, tools, platforms and domain "
        "methods (e.g. 'PostgreSQL', 'Figma', 'Boolean search'). Canonical names, "
        "deduplicated."
    )
    soft_skills: list[str] = Field(
        description="Interpersonal skills: leadership, mentoring, communication, "
        "stakeholder management, teamwork. Never put these in technical_skills."
    )
    experience: list[WorkExperience] = Field(description="Most recent first.")
    education: list[Education]
    certifications: list[str]
    languages: list[str] = Field(description="Spoken languages.")

    # Validators don't change the JSON schema sent to the model; they clean up its output.
    @model_validator(mode="after")
    def _blank_strings_to_none(self):
        # Seen in eval: a missing phone came back as "" instead of null.
        for field in ("full_name", "email", "phone", "location"):
            value = getattr(self, field)
            if value is not None and not value.strip():
                setattr(self, field, None)
        return self

    @model_validator(mode="after")
    def _move_non_email_to_links(self):
        # Seen in eval: with no email on the resume, a model put the portfolio URL here.
        if self.email and not _EMAIL_RE.fullmatch(self.email.strip()):
            if self.email not in self.links:
                self.links.append(self.email)
            self.email = None
        return self


# --- API models ---
class ResumeTextRequest(BaseModel):
    text: str = Field(min_length=50, max_length=50_000, description="Plain-text resume.")


class ParsedResume(BaseModel):
    profile: ResumeExtraction
    total_years_experience: float = Field(
        description="Computed in code from the extracted dates; overlapping roles count once."
    )
    seniority: Seniority = Field(
        description="Computed in code from seniority_signals and total_years_experience."
    )
    usage: UsageInfo
