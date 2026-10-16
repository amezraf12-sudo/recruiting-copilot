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


class JobRequirements(BaseModel):
    # Seen in a screening run: without a description, a model returned the schema's own
    # name ("JobRequirements") as the title.
    title: str = Field(description="The job title exactly as written in the posting.")
    seniority: Seniority | None = Field(
        description="Level the job targets, if stated or clearly implied by the title. "
        "Null otherwise."
    )
    min_years_experience: float | None = Field(
        description="Minimum total years of experience required. Null if not stated."
    )
    must_have_skills: list[str] = Field(
        description="Required skills (required, must, 'X+ years of <skill>'). Canonical "
        "names as they would appear on a resume, deduplicated."
    )
    nice_to_have_skills: list[str] = Field(
        description="Preferred, bonus or 'a plus' skills. Canonical names, deduplicated."
    )
    responsibilities: list[str] = Field(description="Main duties, concise.")
    location: str | None = Field(description="Work location if stated. Null otherwise.")
    # Was `remote: bool`; a "Hybrid" posting forced a yes/no guess and showed "Remote OK".
    work_arrangement: Literal["onsite", "hybrid", "remote"] | None = Field(
        description="As stated in the posting. Null if not stated."
    )
    # Seen in a screening eval: a model returned "Must be 23-32 years old and willing to
    # work night shift; male applicants preferred" as one item, flagging the legitimate
    # night-shift requirement along with age and gender.
    flagged_requirements: list[str] = Field(
        description="Requirements about age, gender, civil status, religion, ethnicity, "
        "nationality, height/weight, appearance or photos, including appearance euphemisms "
        "common in Philippine job ads ('pleasing personality', 'presentable', 'good-looking'). "
        "One item per requirement, quoting only the discriminatory part (e.g. '23-32 years "
        "old', 'male applicants preferred'); legitimate requirements in the same sentence stay "
        "out of this list. These are never used for screening."
    )


# --- API models ---
class ResumeTextRequest(BaseModel):
    text: str = Field(min_length=50, max_length=50_000, description="Plain-text resume.")


class JobTextRequest(BaseModel):
    text: str = Field(min_length=50, max_length=20_000, description="Plain-text job posting.")


class ParsedJob(BaseModel):
    requirements: JobRequirements
    usage: UsageInfo


class CandidateInput(BaseModel):
    id: str = Field(min_length=1, max_length=100, description="Your identifier for this candidate.")
    text: str = Field(min_length=50, max_length=50_000, description="Plain-text resume.")


class ScreenRequest(BaseModel):
    job_description: str = Field(min_length=50, max_length=20_000)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [c.id for c in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("Candidate ids must be unique.")
        return self


class ParsedResume(BaseModel):
    profile: ResumeExtraction
    total_years_experience: float = Field(
        description="Computed in code from the extracted dates; overlapping roles count once."
    )
    seniority: Seniority = Field(
        description="Computed in code from seniority_signals and total_years_experience."
    )
    usage: UsageInfo


class SemanticEvidence(BaseModel):
    skill: str
    evidence: str = Field(description="Resume phrase that demonstrates the skill.")


class CandidateSummary(BaseModel):
    """Work history for the recruiter and the assistant. No contact details on purpose."""

    headline: str
    technical_skills: list[str]
    soft_skills: list[str]
    experience: list[WorkExperience]
    certifications: list[str]


class CandidateMatch(BaseModel):
    candidate_id: str
    full_name: str | None
    summary: CandidateSummary
    score: int = Field(description="0-100, computed in code from the components below.")
    meets_all_must_haves: bool
    matched_must_haves: list[str]
    missing_must_haves: list[str]
    matched_nice_to_haves: list[str]
    suggested_matches: list[SemanticEvidence] = Field(
        description="Missing skills the candidate may have under different wording, found by "
        "meaning (embeddings + LLM check). For recruiter review; never counted in the score."
    )
    total_years_experience: float
    seniority: Seniority
    reasons: list[str] = Field(description="Human-readable explanation of the score.")


class CandidateError(BaseModel):
    candidate_id: str
    error: str


class ScreenUsage(BaseModel):
    llm_calls: int
    input_tokens: int
    output_tokens: int
    embedding_tokens: int
    latency_ms: int


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantRequest(BaseModel):
    """A recruiter's request about a completed screen. The client sends the screen back,
    so the API stays stateless."""

    job: JobRequirements
    candidates: list[CandidateMatch] = Field(min_length=1, max_length=10)
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _ends_with_user(self):
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user.")
        return self


class ProposedAction(BaseModel):
    """Something the assistant suggests doing. Never executed by the API; the recruiter
    approves, edits or rejects it."""

    id: str
    type: Literal["outreach_email", "screening_questions"]
    candidate_id: str
    candidate_name: str | None
    subject: str | None = None
    body: str | None = None
    questions: list[str] = []
    warnings: list[str] = Field(
        default=[], description="Guardrail findings (e.g. protected-attribute language) to review."
    )


class ToolTrace(BaseModel):
    tool: str
    arguments: dict
    ok: bool


class AssistantResponse(BaseModel):
    reply: str
    actions: list[ProposedAction]
    trace: list[ToolTrace] = Field(description="Tools the assistant called, in order.")
    usage: ScreenUsage


class ScreenResult(BaseModel):
    job: JobRequirements
    ranking: list[CandidateMatch] = Field(
        description="Candidates meeting all must-haves first, then by score."
    )
    errors: list[CandidateError]
    usage: ScreenUsage
